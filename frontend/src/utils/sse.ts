import type { ChatSSEDelta, ChatSSEDone, ChatSSEMeta } from '@/types/models/chat'

export interface ChatSSEHandlers {
  /** meta 事件：流开始前先拿到会话/引用信息 */
  onMeta?: (meta: ChatSSEMeta) => void
  /** delta 事件：增量文本 */
  onDelta?: (delta: ChatSSEDelta) => void
  /** done 事件：流结束 */
  onDone?: (done: ChatSSEDone) => void
  /** 业务/网络错误（message + 可选 HTTP 状态码） */
  onError?: (message: string, code?: number) => void
}

/**
 * SSE 客户端（FRONTEND.md §5）。
 * 用 fetch 而非 EventSource：/ai/chat 需携带 Authorization 头，EventSource 无法自定义请求头。
 * 事件序：meta → delta* → done；60s ping 心跳帧直接忽略。
 */
export async function chatSSE(
  url: string,
  body: unknown,
  handlers: ChatSSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('shudao_token')
  let res: Response
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if ((err as Error).name !== 'AbortError') handlers.onError?.('网络连接失败，请检查网络')
    return
  }

  const isSSE = res.headers.get('content-type')?.includes('text/event-stream')
  if (!res.ok || !isSSE) {
    let message = `请求失败（HTTP ${res.status}）`
    try {
      const data: unknown = await res.json()
      const d = data as { message?: string; detail?: string }
      message = d.message ?? d.detail ?? message
    } catch {
      /* 非 JSON 错误体，保留默认文案 */
    }
    handlers.onError?.(message, res.status)
    return
  }

  const reader = res.body?.getReader()
  if (!reader) {
    handlers.onError?.('无法读取响应流')
    return
  }
  const decoder = new TextDecoder('utf-8')
  let buf = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx = buf.indexOf('\n\n')
      while (idx >= 0) {
        const frame = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        dispatch(frame, handlers)
        idx = buf.indexOf('\n\n')
      }
    }
    if (buf.trim()) dispatch(buf, handlers)
  } catch (err) {
    if ((err as Error).name !== 'AbortError') handlers.onError?.('连接中断，请重试')
  }
}

/** 解析单个 SSE 帧（event: X\ndata: {...}）并分发；非 meta/delta/done 事件忽略。 */
function dispatch(raw: string, handlers: ChatSSEHandlers): void {
  let event = 'message'
  let data = ''
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5)
  }
  if (!data) return
  try {
    const payload: unknown = JSON.parse(data)
    if (event === 'meta') handlers.onMeta?.(payload as ChatSSEMeta)
    else if (event === 'delta') handlers.onDelta?.(payload as ChatSSEDelta)
    else if (event === 'done') handlers.onDone?.(payload as ChatSSEDone)
    // ping 心跳帧：忽略
  } catch {
    /* 畸形帧：忽略，不影响后续流 */
  }
}
