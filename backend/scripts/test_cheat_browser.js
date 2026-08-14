// 切屏检测端到端验证：Edge headless + CDP 驱动真实浏览器
// 流程：API 准备数据 → 浏览器登录 → 进入考试页 → 触发 4 次 window blur（模拟切屏）
//      → 每次验证后端 cheat_count 递增 → 第 4 次验证自动交卷跳成绩单
const { spawn } = require('child_process')
const fs = require('fs')
const os = require('os')
const path = require('path')

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const CDP_PORT = 9333
const FRONT = 'http://localhost:5173'
const API = 'http://127.0.0.1:8000/api/v1'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

let pass = 0
let fail = 0
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  [PASS] ${name}${detail ? ' | ' + detail : ''}`) }
  else { fail++; console.log(`  [FAIL] ${name}${detail ? ' | ' + detail : ''}`) }
}

async function api(method, url, body, token) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (body) headers['Content-Type'] = 'application/json'
  const res = await fetch(API + url, { method, headers, body: body ? JSON.stringify(body) : undefined })
  return res.json()
}

// ---------- CDP 客户端 ----------
class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map() }
  static async connect(url) {
    const ws = new WebSocket(url)
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })
    const c = new CDP(ws)
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id && c.pending.has(msg.id)) {
        const { resolve, reject } = c.pending.get(msg.id)
        c.pending.delete(msg.id)
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
      }
    }
    return c
  }
  send(method, params = {}) {
    const id = ++this.id
    this.ws.send(JSON.stringify({ id, method, params }))
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }))
  }
  async eval(expr) {
    const r = await this.send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })
    if (r.exceptionDetails) throw new Error('页面 JS 异常: ' + JSON.stringify(r.exceptionDetails).slice(0, 300))
    return r.result?.value
  }
}

async function main() {
  const tag = Date.now().toString().slice(-6)

  // 1) API 准备：admin 建卷 → 员工注册 → 开考
  console.log('===== 准备数据 =====')
  const adminLogin = await api('POST', '/auth/login', null, null)
  // form 登录
  const loginRes = await fetch(API + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: 'admin', password: 'Admin@123456' }),
  })
  const adminTok = (await loginRes.json()).data.access_token

  const qs = await api('GET', '/questions?status=APPROVED&page_size=1', null, adminTok)
  const qid = qs.data.items[0].id
  const paper = await api('POST', '/papers/manual', {
    name: `切屏E2E-${tag}`, duration: 30, total_score: 100,
    questions: [{ question_id: qid, score: 100 }],
  }, adminTok)
  const pid = paper.data.id
  await api('PUT', `/papers/${pid}`, { status: 'PUBLISHED' }, adminTok)

  const uname = `t_cheat_${tag}`
  await api('POST', '/auth/register', { username: uname, password: 'Test@123456', name: '切屏考生' })
  const empRes = await fetch(API + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: uname, password: 'Test@123456' }),
  })
  const empTok = (await empRes.json()).data.access_token
  const started = await api('POST', '/exams/start', { paper_id: pid }, empTok)
  const recordId = started.data.record_id
  console.log(`  paper=${pid} record=${recordId} 考生=${uname}`)

  // 2) 启动 Edge headless
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-cheat-'))
  const edge = spawn(EDGE, [
    `--remote-debugging-port=${CDP_PORT}`,
    `--user-data-dir=${profile}`,
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--window-size=1400,900',
    'about:blank',
  ], { stdio: 'ignore' })

  // 等调试端口就绪
  let targets = null
  for (let i = 0; i < 20; i++) {
    await sleep(500)
    try {
      targets = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json`)).json()
      if (targets.length) break
    } catch { /* retry */ }
  }
  if (!targets || !targets.length) { console.error('Edge 调试端口未就绪'); edge.kill(); process.exit(1) }

  // 3) 连接页面
  const page = targets.find((t) => t.type === 'page')
  const cdp = await CDP.connect(page.webSocketDebuggerUrl)
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')

  // 4) 登录：注入 token 并跳转考试页
  await cdp.send('Page.navigate', { url: FRONT + '/login' })
  await sleep(2500)
  await cdp.eval(`localStorage.setItem('shudao_token', ${JSON.stringify(empTok)})`)
  await cdp.send('Page.navigate', { url: `${FRONT}/exams/${recordId}` })
  await sleep(4000)

  // 5) 验证页面进入考试态
  const pageState = await cdp.eval(`(() => {
    const hasCard = !!document.querySelector('.exam-taking, .question-card, .cheat-bar, .el-card')
    const text = document.body.innerText.slice(0, 200)
    return { hasCard, text }
  })()`)
  ok('浏览器进入考试页面（DOM 渲染考试组件）', pageState.hasCard || /考试|作答|交卷/.test(pageState.text),
     pageState.text.replace(/\n/g, ' ').slice(0, 80))

  // 6) 触发切屏（window blur 事件；与 visibilitychange 去重逻辑一致：blur 时页面可见才计数）
  console.log('\n===== 模拟 4 次切屏（间隔 2.2s 避开去重窗口）=====')
  const checkCount = async (expected, label) => {
    const r = await api('GET', `/exams/${recordId}`, null, empTok)
    const state = r.data.state
    const cnt = r.data.cheat_count
    ok(`${label} → 后端 cheat_count=${cnt} state=${state}`, cnt === expected, `expected=${expected}`)
    return { state, cnt }
  }

  let cur = 0
  for (let i = 1; i <= 4; i++) {
    await cdp.eval(`window.dispatchEvent(new Event('blur'))`)
    await sleep(1200)
    const r = await api('GET', `/exams/${recordId}`, null, empTok)
    cur = r.data.cheat_count
    const state = r.data.state
    ok(`第 ${i} 次切屏 → cheat_count=${cur} state=${state}`,
       i <= 3 ? (cur === i && state === 'ONGOING') : (cur === 4 && state === 'SUBMITTED'),
       `期望: 前3次递增不交卷, 第4次自动交卷`)
    if (state === 'SUBMITTED') break
    await sleep(1100)
  }

  // 7) 验证成绩单 + 页面跳转
  const finalRes = await api('GET', `/exams/${recordId}/result`, null, empTok)
  ok('后端成绩单可用且 reason=cheat_limit',
     finalRes.data.state === 'SUBMITTED' && finalRes.data.reason === 'cheat_limit',
     `reason=${finalRes.data.reason} cheat=${finalRes.data.cheat_count}`)

  await sleep(1500)
  // 自动交卷弹窗（ElMessageBox.alert）→ 点击「确定」后才会跳转成绩单
  await cdp.eval(`(() => {
    const btns = [...document.querySelectorAll('.el-message-box__btns button')]
    const target = btns.find(b => /确定|OK/i.test(b.innerText)) || btns[0]
    if (target) target.click()
    return !!target
  })()`)
  await sleep(2000)
  const finalUrl = await cdp.eval('location.pathname')
  ok('浏览器自动跳转成绩单页（点击确认后）', finalUrl.includes('/result'), `path=${finalUrl}`)

  cdp.ws.close()
  edge.kill()
  await sleep(1500)
  try { fs.rmSync(profile, { recursive: true, force: true }) } catch { /* Edge 仍占用则忽略 */ }

  console.log(`\n${'='.repeat(50)}\n切屏检测 E2E：PASS ${pass} / FAIL ${fail}`)
  process.exit(fail ? 1 : 0)
}

main().catch((e) => { console.error('脚本异常:', e); process.exit(1) })
