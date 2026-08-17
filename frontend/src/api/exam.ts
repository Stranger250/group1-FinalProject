import { cleanParams, request, uploadRequest } from './request'
import type { PageResult } from '@/types/api'
import type {
  BatchDetail,
  BatchItem,
  ExamAnswerPayload,
  ExamRecordItem,
  ExamSheet,
  ExamStartPayload,
  ExamStats,
  ExamSwitchPayload,
  GeneratePayload,
  GenerateResult,
  GenStats,
  PaperAutoCreatePayload,
  PaperDetail,
  PaperGenMode,
  PaperListItem,
  PaperManualCreatePayload,
  PaperStatus,
  PaperUpdatePayload,
  PublicPaperItem,
  Question,
  QuestionCreatePayload,
  QuestionDifficulty,
  QuestionSource,
  QuestionStatus,
  QuestionType,
  QuestionUpdatePayload,
  RefDocResult,
  ResultSheet,
  ReviewPayload,
  SwitchResult,
  WrongBookItem,
} from '@/types/models/exam'

// ---------- E01 题库（SAFETY/ADMIN） ----------

export interface QuestionQuery {
  type?: QuestionType | ''
  difficulty?: QuestionDifficulty | ''
  knowledge_point?: string
  status?: QuestionStatus | ''
  source?: QuestionSource | ''
  batch_id?: string
  keyword?: string
  page?: number
  page_size?: number
}

export function listQuestions(params: QuestionQuery) {
  return request<PageResult<Question>>({ url: '/questions', method: 'GET', params: cleanParams(params) })
}

export function getQuestion(qid: number) {
  return request<Question>({ url: `/questions/${qid}`, method: 'GET' })
}

export function createQuestion(payload: QuestionCreatePayload) {
  return request<Question>({ url: '/questions', method: 'POST', data: payload })
}

export function updateQuestion(qid: number, payload: QuestionUpdatePayload) {
  return request<Question>({ url: `/questions/${qid}`, method: 'PUT', data: payload })
}

export function deleteQuestion(qid: number) {
  return request<{ message: string }>({ url: `/questions/${qid}`, method: 'DELETE' })
}

/** O8 审核用户提交的题目（SAFETY/ADMIN）：APPROVE 通过 / REJECT 驳回（须填意见） */
export function reviewUserQuestion(qid: number, payload: { action: 'APPROVE' | 'REJECT'; review_note?: string }) {
  return request<Question>({ url: `/questions/${qid}/review`, method: 'POST', data: payload })
}

// ---------- E02 AI 出题（SAFETY/ADMIN） ----------

/** AI 生成题目（LLM 调用较慢，放宽超时） */
export function generateQuestions(payload: GeneratePayload) {
  return request<GenerateResult>({
    url: '/ai/generate',
    method: 'POST',
    data: payload,
    // 后端分轮生成：count>20 时每轮一次 LLM 调用（每轮超时 120s、最多重试 3 次），
    // 50 题最坏可达数分钟。前端若仍设 120s 会抢先掐断慢成功，放宽到 7 分钟。
    timeout: 420_000,
  })
}

/** 上传参考文档并解析为纯文本（txt/md/pdf/docx，≤5MB；业务失败由调用方判断 code） */
export function uploadRefDoc(file: File) {
  const form = new FormData()
  form.append('file', file)
  return uploadRequest<RefDocResult>({ url: '/ai/doc', method: 'POST', data: form, timeout: 60_000 })
}

export function listBatches() {
  return request<BatchItem[]>({ url: '/ai/batches', method: 'GET' })
}

export function getBatchDetail(batchId: string) {
  return request<BatchDetail>({ url: `/ai/batches/${batchId}`, method: 'GET' })
}

export function getGenStats() {
  return request<GenStats>({ url: '/ai/stats', method: 'GET' })
}

export function reviewQuestion(qid: number, payload: ReviewPayload) {
  return request<Question>({ url: `/ai/questions/${qid}/review`, method: 'POST', data: payload })
}

export function rewriteQuestion(qid: number, feedbackText: string) {
  return request<Question>({
    url: `/ai/questions/${qid}/rewrite`,
    method: 'POST',
    data: { feedback: feedbackText },
    // 后端 rewrite 最多 3 次尝试、每次 chat_json 超时 120s（慢成功可达数分钟）。
    // 前端若仍设 120s 会抢先掐断慢成功，出现「前端报失败、后端却已建新批次」的竞态，故放宽到 7 分钟。
    timeout: 420_000,
  })
}

export function reviewBatch(batchId: string, payload: ReviewPayload) {
  return request<{ message: string }>({ url: `/ai/batches/${batchId}/review`, method: 'POST', data: payload })
}

// ---------- E03 试卷（SAFETY/ADMIN） ----------

export interface PaperQuery {
  gen_mode?: PaperGenMode | ''
  status?: PaperStatus | ''
  keyword?: string
  page?: number
  page_size?: number
}

export function listPapers(params: PaperQuery) {
  return request<PageResult<PaperListItem>>({ url: '/papers', method: 'GET', params: cleanParams(params) })
}

export function getPaper(pid: number) {
  return request<PaperDetail>({ url: `/papers/${pid}`, method: 'GET' })
}

export function createPaperManual(payload: PaperManualCreatePayload) {
  return request<PaperDetail>({ url: '/papers/manual', method: 'POST', data: payload })
}

export function createPaperAuto(payload: PaperAutoCreatePayload) {
  return request<PaperDetail & { warnings?: string[] }>({ url: '/papers/auto', method: 'POST', data: payload })
}

export function updatePaper(pid: number, payload: PaperUpdatePayload) {
  return request<PaperDetail>({ url: `/papers/${pid}`, method: 'PUT', data: payload })
}

export function deletePaper(pid: number) {
  return request<{ message: string }>({ url: `/papers/${pid}`, method: 'DELETE' })
}

// ---------- E04/E05 在线考试（任意登录用户） ----------

/** 公开选卷（仅 PUBLISHED，脱敏无题目） */
export function listPublicPapers(page = 1, pageSize = 20) {
  return request<PageResult<PublicPaperItem>>({
    url: '/exams/papers',
    method: 'GET',
    params: cleanParams({ page, page_size: pageSize }),
  })
}

/** 我的考试记录 */
export function listMyExamRecords(page = 1, pageSize = 20) {
  return request<PageResult<ExamRecordItem>>({
    url: '/exams/records',
    method: 'GET',
    params: cleanParams({ page, page_size: pageSize }),
  })
}

/** 开始考试（或刷新复用进行中记录） */
export function startExam(payload: ExamStartPayload) {
  return request<ExamSheet>({ url: '/exams/start', method: 'POST', data: payload, timeout: 30_000 })
}

/** 刷新恢复：进行中返回 ExamSheet，已交卷返回 ResultSheet */
export function resumeExam(recordId: number) {
  return request<ExamSheet | ResultSheet>({ url: `/exams/${recordId}`, method: 'GET', timeout: 30_000 })
}

/** 增量保存答案（15s+ 切题自动保存） */
export function saveExamAnswers(recordId: number, payload: ExamAnswerPayload) {
  return request<ExamSheet>({ url: `/exams/${recordId}/save`, method: 'POST', data: payload, timeout: 30_000 })
}

/** 交卷 + 自动阅卷 */
export function submitExam(recordId: number, payload: ExamAnswerPayload) {
  return request<ResultSheet>({ url: `/exams/${recordId}/submit`, method: 'POST', data: payload, timeout: 60_000 })
}

/** 切屏上报（>3 次自动交卷） */
export function switchExam(recordId: number, payload: ExamSwitchPayload) {
  return request<SwitchResult>({ url: `/exams/${recordId}/switch`, method: 'POST', data: payload, timeout: 30_000 })
}

/** 成绩单 */
export function getExamResult(recordId: number) {
  return request<ResultSheet>({ url: `/exams/${recordId}/result`, method: 'GET' })
}

// ---------- 考试统计 / 错题本 ----------

/** 考试统计（本人；ADMIN all=1 看全站） */
export function getExamStats(all = 0) {
  return request<ExamStats>({ url: '/exams/stats', method: 'GET', params: cleanParams({ all }) })
}

/** 我的错题本（分页） */
export function getWrongBook(page = 1, pageSize = 20) {
  return request<PageResult<WrongBookItem>>({
    url: '/exams/wrong-book',
    method: 'GET',
    params: cleanParams({ page, page_size: pageSize }),
  })
}

// ---------- Excel 批量导入/导出（题库） ----------

/** 导出全部题目 xlsx（浏览器直接下载） */
export function exportQuestionsUrl(): string {
  return '/api/v1/questions/export'
}

/** 下载导入模板 xlsx */
export function exportTemplateUrl(): string {
  return '/api/v1/questions/export/template'
}

/** 批量导入题目 xlsx → {imported, errors:[{row,error}]} */
export function importQuestions(file: File) {
  const form = new FormData()
  form.append('file', file)
  return uploadRequest<{ imported: number; errors: { row: number; error: string }[] }>({
    url: '/questions/import',
    method: 'POST',
    data: form,
    timeout: 60_000,
  })
}
