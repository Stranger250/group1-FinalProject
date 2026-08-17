import { request } from './request'
import type {
  ArticleDetail,
  ChatMessage,
  Conversation,
  ConversationList,
  MessageSource,
  QuickQuestion,
} from '@/types/models/chat'

/** A02 会话列表（{total, items}，非标准分页结构） */
export function listConversations(page = 1, pageSize = 20) {
  return request<ConversationList>({
    url: '/ai/conversations',
    method: 'GET',
    params: { page, page_size: pageSize },
  })
}

/** A02 新建会话（title 缺省「新会话」） */
export function createConversation(title?: string) {
  return request<Conversation>({
    url: '/ai/conversations',
    method: 'POST',
    data: title ? { title } : {},
  })
}

/** A02 重命名会话 */
export function renameConversation(cid: number, title: string) {
  return request<Conversation>({ url: `/ai/conversations/${cid}`, method: 'PUT', data: { title } })
}

/** A02 删除会话（级联删消息） */
export function deleteConversation(cid: number) {
  return request<{ message: string }>({ url: `/ai/conversations/${cid}`, method: 'DELETE' })
}

/** A02 会话消息列表（assistant 消息内联 sources） */
export function listMessages(cid: number) {
  return request<ChatMessage[]>({ url: `/ai/conversations/${cid}/messages`, method: 'GET' })
}

/** A03 回答引用列表 */
export function getSources(messageId: number) {
  return request<MessageSource[]>({ url: `/ai/source/${messageId}`, method: 'GET' })
}

/** A03 查看原文（doc_id + article_no → 父块全文） */
export function getArticle(docId: string, articleNo: string) {
  return request<ArticleDetail>({
    url: '/ai/article',
    method: 'GET',
    params: { doc_id: docId, article_no: articleNo },
  })
}

/** A04 快捷提问 */
export function quickQuestions() {
  return request<QuickQuestion[]>({ url: '/ai/quick-questions', method: 'GET' })
}

/** A07 回答反馈（1=有用 / -1=没用 / 0=清除） */
export function feedback(messageId: number, value: -1 | 0 | 1) {
  return request<{ message: string }>({ url: `/ai/feedback/${messageId}`, method: 'POST', data: { value } })
}

/** O11 上传文档解析（txt/md/pdf/docx → 纯文本，≤8000 字，不落盘） */
export interface ChatFileParseResult {
  filename: string
  ext: string
  chars: number
  truncated: boolean
  text: string
}

export function uploadChatFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<ChatFileParseResult>({
    url: '/ai/chat/files',
    method: 'POST',
    data: form,
    timeout: 30_000,
  })
}
