import { describe, expect, it } from 'vitest'
import {
  filterCitations,
  normalizeLiveCitation,
  normalizeStoredSource,
  toUiMessage,
} from '@/store/modules/chat'
import type { ChatMessage } from '@/types/models/chat'

describe('chat store 引用归一化', () => {
  it('normalizeLiveCitation：合法引用带 doc_id/article_no → clickable=true', () => {
    const c = normalizeLiveCitation({
      n: 1,
      title: '安全生产法',
      article_no: '第五十条',
      doc_id: 'aqscf',
      snippet: '内容…',
    })
    expect(c).not.toBeNull()
    expect(c!.clickable).toBe(true)
    expect(c!.name).toBe('安全生产法')
    expect(c!.articleNo).toBe('第五十条')
  })

  it('normalizeLiveCitation：缺 title/chapter 的脏数据 → null', () => {
    expect(normalizeLiveCitation(null)).toBeNull()
    expect(normalizeLiveCitation('str')).toBeNull()
    expect(normalizeLiveCitation({ foo: 1 })).toBeNull()
  })

  it('normalizeLiveCitation：缺 doc_id/article_no → clickable=false（历史置灰语义）', () => {
    const c = normalizeLiveCitation({ n: 2, title: '条例', content: 'x' })
    expect(c!.clickable).toBe(false)
  })

  it('normalizeStoredSource：历史 sources 无 doc_id/article_no → 不可点击', () => {
    const c = normalizeStoredSource({
      document_name: '法规',
      chapter: '第一章',
      content: '全文',
      score: 0.8,
    } as ChatMessage['sources'][number])
    expect(c.clickable).toBe(false)
    expect(c.score).toBe(0.8)
  })

  it('filterCitations：非数组/脏项过滤', () => {
    expect(filterCitations(null)).toEqual([])
    expect(filterCitations(undefined)).toEqual([])
    expect(filterCitations([{ title: 'a' }, 'bad', null])).toHaveLength(1)
  })
})

describe('toUiMessage（历史消息 → UI 态）', () => {
  it('assistant SUCCESS → success 态，sources 归一化', () => {
    const ui = toUiMessage({
      id: 5,
      role: 'assistant',
      content: '回答',
      status: 'SUCCESS',
      feedback: 1,
      sources: [{ document_name: 'd', content: 'c', score: 0.5 }],
    } as ChatMessage)
    expect(ui.status).toBe('success')
    expect(ui.feedback).toBe(1)
    expect(ui.citations).toHaveLength(1)
  })

  it('非 SUCCESS → error 态', () => {
    const ui = toUiMessage({ id: 6, role: 'assistant', content: '半截', status: 'INTERRUPTED' } as ChatMessage)
    expect(ui.status).toBe('error')
  })

  it('user 消息无 citations', () => {
    const ui = toUiMessage({ id: 7, role: 'user', content: '问', status: 'SUCCESS' } as ChatMessage)
    expect(ui.citations).toEqual([])
  })
})
