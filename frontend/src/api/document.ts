import { request } from './request'

/** O10 文档库文档 */
export interface KnowledgeDoc {
  id: number
  name: string
  type: string
  doc_type: string
  doc_type_label: string
  doc_level: number | null
  region: string | null
  tier: 'national' | 'province' | 'lower'
  status: string
  chunk_count: number
  article_count: number
  char_count: number
  source_url: string | null
  create_time: string | null
  update_time: string | null
}

/** O10 文档详情（含正文预览） */
export interface KnowledgeDocDetail extends KnowledgeDoc {
  chapters: { chapter: string; articles: { article_no: string; content: string; seq: number }[] }[]
}

export interface DocListResult {
  page: number
  page_size: number
  total: number
  items: KnowledgeDoc[]
}

export interface DocListQuery {
  doc_type?: string
  tier?: string
  keyword?: string
  status?: string
  page?: number
  page_size?: number
}

/** 文档列表（分页 + 筛选） */
export function listDocuments(params: DocListQuery) {
  return request<DocListResult>({ url: '/documents', method: 'GET', params })
}

/** 文档详情（元信息 + 正文预览） */
export function getDocument(id: number) {
  return request<KnowledgeDocDetail>({ url: `/documents/${id}`, method: 'GET' })
}

/** 管理端上传文档（txt/md/pdf/docx → 建库管道入库） */
export function uploadDocument(payload: {
  file: File
  title?: string
  doc_type: string
  doc_level?: number
  region?: string
  source_url?: string
}) {
  const form = new FormData()
  form.append('file', payload.file)
  if (payload.title) form.append('title', payload.title)
  form.append('doc_type', payload.doc_type)
  if (payload.doc_level != null) form.append('doc_level', String(payload.doc_level))
  if (payload.region) form.append('region', payload.region)
  if (payload.source_url) form.append('source_url', payload.source_url)
  return request<{ id: number; doc_id: string; title: string; blocks: number; added_chunks: number; status: string }>({
    url: '/documents',
    method: 'POST',
    data: form,
    timeout: 300_000,
  })
}

/** 管理端停用/启用文档 */
export function setDocumentStatus(id: number, status: 'DISABLED' | 'SUCCESS') {
  return request<{ id: number; status: string; changed: boolean; deleted_chunks?: number; rebuilt_chunks?: number }>({
    url: `/documents/${id}/status`,
    method: 'PUT',
    data: { status },
  })
}

/** 管理端删除文档（含分块） */
export function deleteDocument(id: number) {
  return request<{ id: number; deleted_chunks: number }>({ url: `/documents/${id}`, method: 'DELETE' })
}
