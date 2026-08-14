/** 模块二 AI 智能助手模型（对齐 /api/v1/ai/* 契约）。 */

/** 会话（chat_service._conv_out：注意是 created_time / updated_time） */
export interface Conversation {
  id: number
  title: string
  created_time: string | null
  updated_time: string | null
}

/** 会话列表：{total, items}（非标准分页结构，list_conversations 返回） */
export interface ConversationList {
  total: number
  items: Conversation[]
}

/** 回答引用来源（MessageSource） */
export interface MessageSource {
  document_id: string
  chunk_id: string
  /** 原文定位（A03 查看原文用）；旧数据缺省，历史引用不可点击 */
  doc_id?: string | null
  article_no?: string | null
  document_name: string
  chapter: string
  content: string
  score: number | null
}

/** 会话内消息（chat_service.list_messages） */
export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  token_count: number
  status: string
  feedback: -1 | 0 | 1
  create_time: string | null
  sources: MessageSource[]
}

/** SSE meta 事件（qa_service._sse 契约） */
export interface ChatSSEMeta {
  conversation_id: number
  user_message_id: number
  mode: 'full' | 'conservative' | 'refuse' | string
  confidence: number
  citations: unknown[]
  rewritten_used: boolean
}

/** SSE delta 事件 */
export interface ChatSSEDelta {
  text: string
}

/** SSE done 事件 */
export interface ChatSSEDone {
  answer_id: number
  citations: unknown[]
  grounding_score: number
  synthetic: boolean
  error?: string
}

/** 快捷提问（A04） */
export interface QuickQuestion {
  category: string
  question: string
}

/** 查看原文（A03 ArticleOut） */
export interface ArticleDetail {
  doc_id: string
  title: string
  doc_no: string
  category: string
  doc_level: number
  region: string
  chapter: string
  article_no: string
  content: string
  status: string
  publish_date: string
  effective_date: string
  version: string
  source_url: string
}

/** 发送提问请求体（ChatIn） */
export interface ChatPayload {
  conversation_id?: number | null
  message: string
}
