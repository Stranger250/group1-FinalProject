import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  deleteConversation as deleteConversationApi,
  feedback as feedbackApi,
  listConversations,
  listMessages,
  renameConversation as renameConversationApi,
} from '@/api/ai'
import type { ChatMessage, Conversation, MessageSource } from '@/types/models/chat'
import type { ChatSSEDone, ChatSSEMeta } from '@/types/models/chat'
import { chatSSE } from '@/utils/sse'

/**
 * 归一化引用卡片（SSE citations 与历史 sources 统一形态）。
 * SSE meta/done 的 citations（qa_service to_source）带 doc_id/article_no/n/snippet；
 * 历史消息 sources（MessageSource）只有 document_id/chapter/content/score → 不可查看原文。
 */
export interface ChatCitation {
  /** 引用序号（与回答正文 [n] 脚注对应）；历史消息无 */
  n?: number
  /** 原文定位（SSE citations 提供；历史 sources 缺 article_no → 不可点击） */
  docId?: string
  articleNo?: string
  /** 文档名称（SSE: title；历史: document_name） */
  name: string
  /** 章节 */
  chapter: string
  /** 摘要（SSE: snippet；历史: content 全文摘要） */
  content: string
  /** 相似度 0~1；SSE citations 无该字段为 null */
  score: number | null
  /** 原文链接（SSE citations 提供） */
  sourceUrl?: string
  /** O7 行政层级（SSE citations 提供）：national 国家级 / province 省级 / lower 更低级 */
  tier?: 'national' | 'province' | 'lower'
  /** 是否可点击查看原文（doc_id + article_no 齐备） */
  clickable: boolean
}

/** 消息展示状态：发送中 / 流式中 / 完成 / 出错 */
export type UiMessageStatus = 'sending' | 'streaming' | 'success' | 'error'

/** 会话内 UI 消息（含本地发送/占位阶段） */
export interface UiChatMessage {
  /** 后端消息 id；本地暂存 / assistant 占位（未收到 done.answer_id）时为 null */
  id: number | null
  role: 'user' | 'assistant'
  content: string
  status: UiMessageStatus
  citations: ChatCitation[]
  feedback: -1 | 0 | 1
  createTime: string | null
  error: string | null
}

/** 归一化 SSE meta/done citations（unknown[] → ChatCitation[]，脏数据丢弃） */
export function normalizeLiveCitation(raw: unknown): ChatCitation | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const docId = typeof o.doc_id === 'string' && o.doc_id ? o.doc_id : undefined
  const articleNo = typeof o.article_no === 'string' && o.article_no ? o.article_no : undefined
  const title = typeof o.title === 'string' ? o.title : ''
  const chapter = typeof o.chapter === 'string' ? o.chapter : ''
  if (!title && !chapter) return null
  return {
    n: typeof o.n === 'number' ? o.n : undefined,
    docId,
    articleNo,
    name: title,
    chapter,
    content:
      typeof o.snippet === 'string' ? o.snippet : typeof o.content === 'string' ? o.content : '',
    score: typeof o.score === 'number' ? o.score : null,
    sourceUrl: typeof o.source_url === 'string' ? o.source_url : undefined,
    tier: ['national', 'province', 'lower'].includes(String(o.tier)) ? (o.tier as ChatCitation['tier']) : undefined,
    clickable: !!docId && !!articleNo,
  }
}

/** 归一化历史 sources（MessageSource → ChatCitation；doc_id+article_no 齐备才可点击查看原文） */
export function normalizeStoredSource(s: MessageSource): ChatCitation {
  const docId = s.doc_id || undefined
  const articleNo = s.article_no || undefined
  return {
    docId,
    articleNo,
    name: s.document_name || '法规来源',
    chapter: s.chapter || '',
    content: s.content || '',
    score: s.score ?? null,
    clickable: !!docId && !!articleNo,
  }
}

/** 后端历史消息 → UI 消息（SUCCESS 视为完成，其余视为失败态） */
export function toUiMessage(m: ChatMessage): UiChatMessage {
  const isAssistant = m.role === 'assistant'
  const ok = m.status === 'SUCCESS'
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    status: ok ? 'success' : 'error',
    citations: isAssistant ? (m.sources ?? []).map(normalizeStoredSource) : [],
    feedback: m.feedback ?? 0,
    createTime: m.create_time,
    error: ok ? null : '该回答未能完整生成',
  }
}

export function filterCitations(list: unknown[] | null | undefined): ChatCitation[] {
  if (!Array.isArray(list)) return []
  const out: ChatCitation[] = []
  for (const raw of list) {
    const c = normalizeLiveCitation(raw)
    if (c) out.push(c)
  }
  return out
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  /** 当前会话 id；null = 新对话草稿（首问流式时由后端建会话） */
  const currentId = ref<number | null>(null)
  const messages = ref<UiChatMessage[]>([])
  const streaming = ref(false)
  const loadingConversations = ref(false)
  const loadingMessages = ref(false)

  let abort: AbortController | null = null

  // ---------------- 会话列表 ----------------

  async function fetchConversations() {
    loadingConversations.value = true
    try {
      const data = await listConversations(1, 100)
      conversations.value = data.items
    } catch {
      /* 错误已由 request 全局提示 */
    } finally {
      loadingConversations.value = false
    }
  }

  /** 新建会话：清空为草稿态（后端会话在首次发送流式时懒创建） */
  function newConversation() {
    stopStreaming()
    currentId.value = null
    messages.value = []
  }

  async function selectConversation(id: number) {
    if (id === currentId.value) return
    stopStreaming()
    currentId.value = id
    loadingMessages.value = true
    messages.value = []
    try {
      const list = await listMessages(id)
      messages.value = list.map(toUiMessage)
    } catch {
      messages.value = []
    } finally {
      loadingMessages.value = false
    }
  }

  async function renameConversation(id: number, title: string) {
    if (!title.trim()) return
    await renameConversationApi(id, title.trim())
    const c = conversations.value.find((x) => x.id === id)
    if (c) c.title = title.trim()
  }

  async function removeConversation(id: number) {
    await deleteConversationApi(id)
    conversations.value = conversations.value.filter((x) => x.id !== id)
    if (currentId.value === id) newConversation()
  }

  // ---------------- 消息流式 ----------------

  async function sendMessage(text: string) {
    const content = text.trim()
    if (!content || streaming.value) return

    stopStreaming()
    streaming.value = true
    abort = new AbortController()

    const userMsg: UiChatMessage = {
      id: null,
      role: 'user',
      content,
      status: 'sending',
      citations: [],
      feedback: 0,
      createTime: null,
      error: null,
    }
    const assistantMsg: UiChatMessage = {
      id: null,
      role: 'assistant',
      content: '',
      status: 'streaming',
      citations: [],
      feedback: 0,
      createTime: null,
      error: null,
    }
    messages.value.push(userMsg, assistantMsg)
    const assistantIndex = messages.value.length - 1

    let pendingText = ''
    let rafId = 0
    const flushText = () => {
      const m = messages.value[assistantIndex]
      if (m && m.role === 'assistant') m.content = pendingText
    }

    const onMeta = (meta: ChatSSEMeta) => {
      const isNew = currentId.value === null
      currentId.value = meta.conversation_id
      userMsg.id = meta.user_message_id
      userMsg.status = 'success'
      assistantMsg.citations = filterCitations(meta.citations)
      // 新会话懒创建完成 → 刷新会话列表（首问自动标题）
      if (isNew) void fetchConversations()
    }

    const onDelta = (delta: { text: string }) => {
      pendingText += delta.text
      // 节流渲染：用 setTimeout 而非 requestAnimationFrame——
      // rAF 在页面不可见（后台标签页/无头浏览器）时暂停，会导致流式渲染冻结
      if (!rafId) {
        rafId = window.setTimeout(() => {
          rafId = 0
          flushText()
        }, 16)
      }
    }

    const onDone = (done: ChatSSEDone) => {
      if (rafId) clearTimeout(rafId)
      rafId = 0
      flushText()
      assistantMsg.id = done.answer_id
      assistantMsg.citations = filterCitations(done.citations)
      if (done.error) {
        assistantMsg.status = 'error'
        assistantMsg.error = done.error
      } else {
        assistantMsg.status = 'success'
      }
      // 标题（首问）/ updated_time 变化 → 刷新列表
      void fetchConversations()
    }

    const onError = (errMsg: string) => {
      if (rafId) clearTimeout(rafId)
      rafId = 0
      flushText()
      assistantMsg.status = 'error'
      assistantMsg.error = errMsg
      // meta 未到达前失败：本地 user 消息也标记为失败（避免一直显示"发送中"）
      if (userMsg.status === 'sending') {
        userMsg.status = 'error'
        userMsg.error = errMsg
      }
    }

    try {
      await chatSSE(
        '/api/v1/ai/chat',
        { conversation_id: currentId.value, message: content },
        { onMeta, onDelta, onDone, onError },
        abort.signal,
      )
    } finally {
      if (rafId) clearTimeout(rafId)
      streaming.value = false
      abort = null
      // 兜底：流正常结束但未收到 done（如服务器提前关闭）→ 有内容按成功，空按失败
      const last = messages.value[assistantIndex]
      if (last && last.role === 'assistant' && last.status === 'streaming') {
        last.status = last.content ? 'success' : 'error'
        if (!last.content) last.error = '回答生成中断，请重试'
      }
      // 兜底：user 消息始终停在发送中（meta 未到达即结束）→ 标记失败
      if (userMsg.status === 'sending') {
        userMsg.status = 'error'
        userMsg.error = '回答生成中断，请重试'
      }
    }
  }

  /** 停止生成：中止流；正在流式的占位消息标记为失败（保留已生成内容） */
  function stopStreaming() {
    if (abort) {
      abort.abort()
      abort = null
    }
    streaming.value = false
    for (const m of messages.value) {
      if (m.status === 'streaming') {
        m.status = 'error'
        m.error = '已停止生成'
      } else if (m.status === 'sending') {
        m.status = 'error'
        m.error = '发送已中止'
      }
    }
  }

  // ---------------- 反馈 ----------------

  async function setFeedback(messageId: number, value: -1 | 0 | 1) {
    try {
      await feedbackApi(messageId, value)
      const m = messages.value.find((x) => x.id === messageId)
      if (m) m.feedback = value
    } catch {
      /* 错误已由 request 全局提示 */
    }
  }

  return {
    conversations,
    currentId,
    messages,
    streaming,
    loadingConversations,
    loadingMessages,
    fetchConversations,
    newConversation,
    selectConversation,
    renameConversation,
    removeConversation,
    sendMessage,
    stopStreaming,
    setFeedback,
  }
})
