import { afterEach, describe, expect, it, vi } from 'vitest'
import { chatSSE } from '@/utils/sse'

/** 构造受控 fetch 流响应：按帧序列返回 text/event-stream */
function mockStreamResponse(frames: string[]): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream({
    start(controller) {
      for (const f of frames) controller.enqueue(encoder.encode(f))
      controller.close()
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

describe('chatSSE（fetch 流分帧客户端）', () => {
  const origFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = origFetch
    localStorage.clear()
  })

  it('正常流：meta → delta* → done 依次回调', async () => {
    const events: string[] = []
    const deltas: string[] = []
    const done = vi.fn()
    const meta = vi.fn()
    globalThis.fetch = vi.fn().mockResolvedValue(
      mockStreamResponse([
        'event: meta\ndata: {"conversation_id":1,"mode":"full"}\n\n',
        'event: delta\ndata: {"text":"你"}\n\n',
        'event: delta\ndata: {"text":"好"}\n\n',
        'event: done\ndata: {"answer_id":9,"citations":[]}\n\n',
      ]),
    )

    await chatSSE('/api/v1/ai/chat', { message: 'x' }, {
      onMeta: (m) => { events.push('meta'); meta(m) },
      onDelta: (d) => { events.push('delta'); deltas.push(d.text) },
      onDone: (d) => { events.push('done'); done(d) },
    })

    expect(events).toEqual(['meta', 'delta', 'delta', 'done'])
    expect(deltas).toEqual(['你', '好'])
    expect(done).toHaveBeenCalledWith(expect.objectContaining({ answer_id: 9 }))
    expect(meta).toHaveBeenCalledWith(expect.objectContaining({ conversation_id: 1 }))
  })

  it('ping 心跳帧被忽略（不触发任何回调）', async () => {
    const onDelta = vi.fn()
    const onDone = vi.fn()
    globalThis.fetch = vi.fn().mockResolvedValue(
      mockStreamResponse([
        'event: meta\ndata: {"conversation_id":1}\n\n',
        'event: ping\ndata: {"type":"ping"}\n\n',
        'event: delta\ndata: {"text":"ok"}\n\n',
        'event: done\ndata: {"answer_id":1}\n\n',
      ]),
    )
    await chatSSE('/api/v1/ai/chat', {}, { onDelta, onDone })
    expect(onDelta).toHaveBeenCalledTimes(1)
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('跨多块拼接的帧（\n\n 边界在块中间）正确分帧', async () => {
    const encoder = new TextEncoder()
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: delta\ndata: {"te'))
        controller.enqueue(encoder.encode('xt":"拼"}'))
        controller.enqueue(encoder.encode('\n\nevent: done\ndata: {"answer_id":2}\n\n'))
        controller.close()
      },
    })
    const deltas: string[] = []
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    )
    await chatSSE('/api/v1/ai/chat', {}, { onDelta: (d) => deltas.push(d.text) })
    expect(deltas).toEqual(['拼'])
  })

  it('HTTP 非 2xx 且非 SSE → onError(message, status)', async () => {
    const onError = vi.fn()
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: '内容包含敏感词' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await chatSSE('/api/v1/ai/chat', {}, { onError })
    expect(onError).toHaveBeenCalledWith('内容包含敏感词', 400)
  })

  it('网络失败 → onError（AbortError 不回调）', async () => {
    const onError = vi.fn()
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('fetch failed'))
    await chatSSE('/api/v1/ai/chat', {}, { onError })
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('网络'))
  })

  it('携带 Authorization 头（localStorage token）', async () => {
    localStorage.setItem('shudao_token', 'tok123')
    const fetchMock = vi.fn().mockResolvedValue(
      mockStreamResponse(['event: done\ndata: {"answer_id":1}\n\n']),
    )
    globalThis.fetch = fetchMock
    await chatSSE('/api/v1/ai/chat', {}, {})
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/ai/chat')
    expect((init as RequestInit).headers).toMatchObject({ Authorization: 'Bearer tok123' })
  })
})
