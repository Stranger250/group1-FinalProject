import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '@/utils/markdown'

describe('renderMarkdown（XSS 净化管线：marked → DOMPurify）', () => {
  it('空输入 → 空串', () => {
    expect(renderMarkdown(null)).toBe('')
    expect(renderMarkdown(undefined)).toBe('')
    expect(renderMarkdown('')).toBe('')
  })

  it('普通 Markdown 正常渲染', () => {
    expect(renderMarkdown('**加粗**')).toContain('<strong>加粗</strong>')
    expect(renderMarkdown('`code`')).toContain('<code>code</code>')
  })

  it('script 标签被剥离', () => {
    const out = renderMarkdown('<script>alert(1)</script>')
    expect(out).not.toContain('<script>')
    expect(out).not.toContain('alert(1)')
  })

  it('事件属性 onerror 被剥离', () => {
    const out = renderMarkdown('<img src=x onerror=alert(1)>')
    expect(out).not.toContain('onerror')
  })

  it('javascript: URL 被剥离', () => {
    const out = renderMarkdown('[点击](javascript:alert(1))')
    expect(out).not.toContain('javascript:')
  })

  it('AI 回答含脚注 [1] 保留（正常业务文本）', () => {
    const out = renderMarkdown('根据《安全生产法》[1]，应当…')
    expect(out).toContain('[1]')
  })
})
