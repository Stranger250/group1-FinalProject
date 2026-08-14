import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({
  gfm: true,
  breaks: true,
})

/**
 * AI 回答 Markdown 渲染唯一净化管线（FRONTEND.md C7）：
 * marked 解析 → DOMPurify 白名单消毒 → 可安全用于 v-html。
 * 切勿绕过本函数直接 v-html 未经净化的 AI 文本。
 */
export function renderMarkdown(text: string | null | undefined): string {
  if (!text) return ''
  const html = marked.parse(text) as string
  return DOMPurify.sanitize(html)
}
