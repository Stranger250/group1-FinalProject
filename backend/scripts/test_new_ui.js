// 新功能 UI 冒烟：考试统计 / 错题本 / 审计日志 / 题库导入导出按钮
const { spawn } = require('child_process')
const fs = require('fs')
const os = require('os')
const path = require('path')

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const CDP_PORT = 9336
const FRONT = 'http://localhost:5173'
const API = 'http://127.0.0.1:8000/api/v1'
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
    if (r.exceptionDetails) throw new Error('页面 JS 异常: ' + JSON.stringify(r.exceptionDetails).slice(0, 200))
    return r.result?.value
  }
}

async function main() {
  const login = async (u, p) => {
    const res = await fetch(API + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: u, password: p }),
    })
    return (await res.json()).data.access_token
  }
  const adminTok = await login('admin', 'Admin@123456')

  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-newui-'))
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
  await cdp.eval(`localStorage.setItem('shudao_token', ${JSON.stringify(adminTok)})`)

  const checkPage = async (pathname, expectTexts) => {
    await cdp.send('Page.navigate', { url: FRONT + pathname })
    await sleep(3500)
    const text = await cdp.eval('document.body.innerText')
    const pathNow = await cdp.eval('location.pathname')
    ok(`页面 ${pathname} 渲染`, pathNow === pathname, `path=${pathNow}`)
    for (const t of expectTexts) {
      ok(` 含「${t}」`, text.includes(t))
    }
  }

  await checkPage('/exams/stats', ['考试统计', '通过率', '平均分', '知识点掌握度', '错题排行'])
  await checkPage('/exams/wrong-book', ['我的错题'])
  await checkPage('/admin/logs', ['审计日志', '操作人', '动作'])
  await checkPage('/exam/questions', ['题库管理', '导入', '导出', '模板', '新建题目'])

  cdp.ws.close(); edge.kill(); await sleep(1500)
  try { fs.rmSync(profile, { recursive: true, force: true }) } catch { /* ignore */ }
  console.log(`\n${'='.repeat(50)}\n新功能 UI 冒烟：PASS ${pass} / FAIL ${fail}`)
  process.exit(fail ? 1 : 0)
}
main().catch((e) => { console.error('脚本异常:', e); process.exit(1) })
