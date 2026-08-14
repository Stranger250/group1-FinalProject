// 切屏去重窗口验证：2s 内 blur + visibilitychange 双事件应只计 1 次
const { spawn } = require('child_process')
const fs = require('fs')
const os = require('os')
const path = require('path')

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const CDP_PORT = 9334
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

  const adminTok = await login('admin', 'Admin@123456')
  const qs = await api('GET', '/questions?status=APPROVED&page_size=1', null, adminTok)
  const paper = await api('POST', '/papers/manual', {
    name: `去重E2E-${tag}`, duration: 30, total_score: 100,
    questions: [{ question_id: qs.data.items[0].id, score: 100 }],
  }, adminTok)
  await api('PUT', `/papers/${paper.data.id}`, { status: 'PUBLISHED' }, adminTok)
  const uname = `t_dedup_${tag}`
  await api('POST', '/auth/register', { username: uname, password: 'Test@123456', name: '去重考生' })
  const empTok = await login(uname, 'Test@123456')
  const started = await api('POST', '/exams/start', { paper_id: paper.data.id }, empTok)
  const recordId = started.data.record_id
  console.log(`record=${recordId}`)

  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'edge-dedup-'))
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
  await sleep(4000)

  const getCount = async () => (await api('GET', `/exams/${recordId}`, null, empTok)).data.cheat_count

  console.log('===== 场景1：2s 内 blur+visibilitychange 双触发 → 应只计 1 次 =====')
  await cdp.eval(`window.dispatchEvent(new Event('blur'))`)
  await sleep(300)
  await cdp.eval(`Object.defineProperty(document, 'hidden', {value: true, configurable: true}); document.dispatchEvent(new Event('visibilitychange'))`)
  await sleep(1200)
  ok('blur+visibilitychange 双触发只计 1 次', (await getCount()) === 1, `count=${await getCount()}`)

  console.log('===== 场景2：间隔 3s 再触发 → 计第 2 次 =====')
  await sleep(3000)
  await cdp.eval(`Object.defineProperty(document, 'hidden', {value: false, configurable: true})`)
  await cdp.eval(`window.dispatchEvent(new Event('blur'))`)
  await sleep(1200)
  ok('间隔 3s 后触发计第 2 次', (await getCount()) === 2, `count=${await getCount()}`)

  cdp.ws.close(); edge.kill(); await sleep(1500)
  try { fs.rmSync(profile, { recursive: true, force: true }) } catch { /* ignore */ }
  console.log(`\n${'='.repeat(50)}\n去重窗口 E2E：PASS ${pass} / FAIL ${fail}`)
  process.exit(fail ? 1 : 0)
}
main().catch((e) => { console.error('脚本异常:', e); process.exit(1) })
