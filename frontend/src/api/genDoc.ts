import { request } from './request'

/** O12 文档生成 */

export interface GenDocOutline {
  title?: string
  sections?: { heading: string; paragraphs: string[] }[]
  slides?: { title: string; bullets: string[] }[]
}

/** 大纲预览（DeepSeek 生成） */
export function previewGenDoc(payload: { doc_type: 'word' | 'ppt'; topic: string; style?: string }) {
  return request<{ outline: GenDocOutline }>({ url: '/gen-doc/preview', method: 'POST', data: payload, timeout: 180_000 })
}

/** 按大纲渲染下载（.docx/.pptx） */
export async function downloadGenDoc(payload: { doc_type: 'word' | 'ppt'; topic: string; outline: GenDocOutline }) {
  const token = localStorage.getItem('shudao_token')
  const res = await fetch('/api/v1/gen-doc/download', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let msg = `生成失败（HTTP ${res.status}）`
    try {
      const d = (await res.json()) as { message?: string; detail?: string }
      msg = d.message ?? d.detail ?? msg
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new Error(msg)
  }
  const blob = await res.blob()
  const cd = res.headers.get('content-disposition') || ''
  const m = cd.match(/filename\*=UTF-8''([^;]+)/)
  const fname = m ? decodeURIComponent(m[1]) : payload.doc_type === 'word' ? '文档.docx' : '课件.pptx'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fname
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  return fname
}
