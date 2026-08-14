// 解答题 UI 快速验证：真实浏览器打开考试页，确认 SUBJECTIVE textarea 渲染
const { spawn } = require('child_process')
const fs = require('fs')
const os = require('os')
const path = require('path')

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const CDP_PORT = 9335
const FRONT = 'http://localhost:5174'
const API = 'http://127.0.0.1:8001/api/v1'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

let pass = 0, fail = 0
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  [PASS] ${name}${detail ? ' | ' + detail : ''}`) }
  else { fail++; console.log(`  [FAIL] ${name}${detail ? ' | ' + detail : ''}`) }
}

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
  const login = async (u, p) => {
    const res = await fetch(API + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: u, password: p }),
    })
    return (await res.json()).data.access_token
  }
  const api = async (method, url, body, token) => {
    const headers = {}
    if (token) headers.Authorization = `Bearer ${token}`
    if (body) headers['Content-Type'] = 'application/json'
    const res = await fetch(API + url, { method, headers, body: body ? JSON.stringify(body) : undefined })
    return res.json()
  }

  // 准备：admin 建解答题并组卷发布
  const adminTok = await login('admin', 'Admin@123456')
  const q = await api('POST', '/questions', {
    type: 'SUBJECTIVE', content: '简述动火作业前的安全要求。', options: null,
    answer: '办理动火作业许可证；清除周围可燃物；配备灭火器材；安排专人监护',
    analysis: '动火作业必须落实审批、清理、防护、监护措施。',
    knowledge_point: '动火作业', difficulty: 'MEDIUM',
  }, adminTok)
  const paper = await api('POST', '/papers/manual', {
    name: `解答题UI-${tag}`, duration: 30, total_score: 20, pass_score: 12,
    questions: [{ question_id: q.data.id, score: 20 }],
  }, adminTok)
  await api('PUT', `/papers/${paper.data.id}`, { status: 'PUBLISHED' }, adminTok)

  const uname = `t_ui_${tag}`
  await api('POST', '/auth/register', { username: uname, password: 'Test@123456', name: 'UI考生' })
  const empTok = await login(uname, 'Test@123456')
  const started = await api('POST', '/exams/start', { paper_id: paper.data.id }, empTok)
  const recordId = started.data.record_id

  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-ui-'))
  const edge = spawn(EDGE, [`--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${profile}`,
    '--headless=new', '--disable-gpu', '--no-first-run', '--window-size=1400,900', 'about:blank'],
    { stdio: 'ignore' })
  let targets = null
  for (let i = 0; i < 20; i++) {
    await sleep(500)
    try {
      targets = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json`)).json()
      if (targets.length) break
    } catch { /* retry */ }
  }
  const page = targets.find((t) => t.type === 'page')
  const cdp = await CDP.connect(page.webSocketDebuggerUrl)
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable')
  await cdp.send('Page.navigate', { url: FRONT + '/login' })
  await sleep(2500)
  await cdp.eval(`localStorage.setItem('shudao_token', ${JSON.stringify(empTok)})`)
  await cdp.send('Page.navigate', { url: `${FRONT}/exams/${recordId}` })
  await sleep(4500)

  // 检查页面：题型标签 + textarea 是否存在
  const ui = await cdp.eval(`(() => {
    const text = document.body.innerText
    const ta = document.querySelector('.subjective-wrap textarea')
    const fillHint = !!document.querySelector('.subjective-wrap .fill-hint')
    return {
      hasLabel: text.includes('解答题'),
      hasTextarea: !!ta,
      hasHint: fillHint,
      taRows: ta ? ta.getAttribute('rows') : null,
    }
  })()`)
  ok('题型标签显示「解答题」', ui.hasLabel, JSON.stringify(ui))
  ok('解答题作答 textarea 已渲染', ui.hasTextarea && ui.taRows === '6', `rows=${ui.taRows}`)
  ok('作答提示文案显示', ui.hasHint)

  // 实际输入答案并验证可提交（不交卷，只验证输入绑定）
  await cdp.eval(`(() => {
    const ta = document.querySelector('.subjective-wrap textarea')
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
    setter.call(ta, '办理动火作业许可证；清除周围可燃物')
    ta.dispatchEvent(new Event('input', { bubbles: true }))
  })()`)
  // 自动保存为 15s 心跳节流（AUTOSAVE_INTERVAL=15），等待一个心跳周期后验证服务端已存
  await sleep(17000)
  const saved = await api('GET', `/exams/${recordId}`, null, empTok)
  ok('输入解答后自动保存生效（15s 心跳后服务端已存答案）',
     saved.data.answers.some((a) => a.user_answer.includes('动火作业许可证')),
     JSON.stringify(saved.data.answers))

  cdp.ws.close(); edge.kill(); await sleep(1500)
  try { fs.rmSync(profile, { recursive: true, force: true }) } catch { /* ignore */ }
  console.log(`\n${'='.repeat(50)}\n解答题 UI 验证：PASS ${pass} / FAIL ${fail}`)
  process.exit(fail ? 1 : 0)
}
main().catch((e) => { console.error('脚本异常:', e); process.exit(1) })
