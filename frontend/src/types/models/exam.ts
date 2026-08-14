/** 模块三 考试工坊模型（对齐 /api/v1/questions、/ai/*、/papers/*、/exams/* 契约）。 */

export type QuestionType = 'SINGLE' | 'MULTIPLE' | 'JUDGE' | 'FILL' | 'SUBJECTIVE'
export type QuestionDifficulty = 'EASY' | 'MEDIUM' | 'HARD'
export type QuestionStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'DISABLED'
export type QuestionSource = 'manual' | 'ai'
export type PaperGenMode = 'manual' | 'ai'
export type PaperStatus = 'DRAFT' | 'PUBLISHED' | 'DISABLED'

/** 题目溯源条目（AI 出题 sources，{role, law_title, article_no}） */
export interface QuestionSourceRef {
  role: string
  law_title: string
  article_no: string
}

/** 题库行 / 出题批次题（QuestionOut / _to_dict） */
export interface Question {
  id: number
  batch_id: string | null
  type: QuestionType
  content: string
  options: string[] | null
  answer: string
  analysis: string | null
  knowledge_point: string
  difficulty: QuestionDifficulty
  source: QuestionSource
  sources: QuestionSourceRef[] | null
  source_law_title: string | null
  source_article_no: string | null
  status: QuestionStatus
  reviewer: number | null
  review_note: string | null
  interference_verified: number
  rewrite_of: number | null
  rewrite_feedback: string | null
  create_time: string | null
  update_time: string | null
}

/** 手工录入请求（QuestionCreate） */
export interface QuestionCreatePayload {
  type: QuestionType
  content: string
  options: string[] | null
  answer: string
  analysis: string
  knowledge_point: string
  difficulty: QuestionDifficulty
  source_law_title?: string | null
  source_article_no?: string | null
}

/** 编辑题目请求（QuestionUpdate，仅提交变更字段） */
export interface QuestionUpdatePayload {
  type?: QuestionType
  content?: string
  options?: string[] | null
  answer?: string
  analysis?: string
  knowledge_point?: string
  difficulty?: QuestionDifficulty
  status?: QuestionStatus
  review_note?: string | null
}

/** AI 生成请求（GenRequest） */
export interface GeneratePayload {
  knowledge_point: string
  types: QuestionType[]
  difficulty: QuestionDifficulty
  count: number
  law_title?: string | null
  /** 参考文档纯文本（上传解析所得，可空） */
  reference_text?: string | null
  /** 参考文档文件名（可空） */
  reference_title?: string | null
}

/** 参考文档解析结果（POST /ai/doc） */
export interface RefDocResult {
  filename: string
  size: number
  chars: number
  truncated: boolean
  text: string
}

/** 生成结果 */
export interface GenerateResult {
  batch_id: string
  count: number
  knowledge_point: string
  difficulty: QuestionDifficulty
}

/** 生成批次列表行（gen_service.list_batches） */
export interface BatchItem {
  batch_id: string
  total: number
  pending: number
  approved: number
  rejected: number
  pass_rate: number
}

/** 批次详情（list_batch） */
export interface BatchDetail {
  batch_id: string
  total: number
  pending: number
  approved: number
  rejected: number
  pass_rate: number
  questions: Question[]
}

/** AI 出题统计（stats） */
export interface GenStats {
  total_ai: number
  total_pending: number
  total_approved: number
  total_rejected: number
  total_rewritten: number
  pass_rate: number
  batches: BatchItem[]
}

/** 单题/批量审核参数（ReviewIn / BatchReviewIn） */
export interface ReviewPayload {
  action: 'APPROVE' | 'REJECT'
  review_note?: string | null
  interference_verified?: boolean
  ids?: number[]
}

/** 试卷列表行（paper_service.list_page） */
export interface PaperListItem {
  id: number
  name: string
  total_score: number
  pass_score: number
  duration: number
  question_count: number
  gen_mode: PaperGenMode
  status: PaperStatus
  creator_id: number
  creator_name: string | null
  create_time: string | null
}

/** 试卷内题目预览（_question_dict：含答案，仅管理员可见） */
export interface PaperQuestionPreview {
  id: number
  type: QuestionType
  content: string
  options: string[] | null
  answer: string
  analysis: string | null
  knowledge_point: string
  difficulty: QuestionDifficulty
  source_law_title: string | null
  source_article_no: string | null
}

/** 试卷详情（_detail） */
export interface PaperDetail extends PaperListItem {
  difficulty_ratio: Record<string, unknown> | null
  questions: { seq: number; score: number; question: PaperQuestionPreview | null }[]
}

/** 手动组卷（PaperManualCreate） */
export interface PaperManualCreatePayload {
  name: string
  duration: 30 | 60 | 90
  pass_score: number
  total_score: number
  questions: { question_id: number; score: number | null }[]
}

/** AI 智能组卷规则（PaperAutoRule） */
export interface PaperAutoRule {
  type: QuestionType
  difficulty: QuestionDifficulty | null
  count: number
}

/** AI 智能组卷（PaperAutoCreate） */
export interface PaperAutoCreatePayload {
  name: string
  duration: 30 | 60 | 90
  pass_score: number
  total_score: number
  rules: PaperAutoRule[]
  knowledge_points?: string[] | null
}

/** 更新试卷（PaperUpdate） */
export interface PaperUpdatePayload {
  name?: string
  duration?: 30 | 60 | 90
  pass_score?: number
  total_score?: number
  status?: PaperStatus
}

/** 公开选卷（exam_service.list_published_papers，脱敏无题目） */
export interface PublicPaperItem {
  id: number
  name: string
  total_score: number
  pass_score: number
  duration: number
  question_count: number
  gen_mode: PaperGenMode
  create_time: string | null
  ongoing_record_id: number | null
}

/** 我的考试记录行（exam_service.list_my_records） */
export interface ExamRecordItem {
  record_id: number
  paper_id: number
  paper_name: string
  state: 'ONGOING' | 'SUBMITTED'
  status: 'PASS' | 'FAIL' | ''
  score: number
  pass_score: number | null
  passed: boolean
  reason: string | null
  cheat_count: number
  start_time: string | null
  submitted_at: string | null
}

/** 进行中试卷视图（_exam_sheet：脱敏，无答案） */
export interface ExamSheet {
  record_id: number
  paper_id: number
  paper_name: string
  state: 'ONGOING' | 'SUBMITTED'
  total_score: number
  pass_score: number
  duration: number
  start_time: string
  deadline: string
  remaining_seconds: number
  server_time: string
  cheat_count: number
  questions: {
    seq: number
    id: number
    type: QuestionType
    content: string
    options: string[] | null
    score: number
  }[]
  answers: { question_id: number; user_answer: string }[]
}

/** 成绩单（_result_sheet） */
export interface ResultSheet {
  record_id: number
  paper_id: number
  paper_name: string
  state: 'ONGOING' | 'SUBMITTED'
  status: 'PASS' | 'FAIL' | ''
  reason: string | null
  total_score: number
  score: number
  pass_score: number
  passed: boolean
  submitted_at: string | null
  start_time: string | null
  duration: number
  cheat_count: number
  questions: {
    seq: number
    question_id: number
    type: QuestionType
    content: string
    options: string[] | null
    user_answer: string
    correct_answer: string
    is_correct: number
    score: number
    analysis: string | null
  }[]
}

/** 切屏上报响应（switch） */
export interface SwitchResult {
  record_id: number
  cheat_count: number
  remaining_seconds: number
  triggered: boolean
  threshold: number
}

/** 保存/开始考试请求 */
export interface ExamStartPayload {
  paper_id: number
}
export interface ExamAnswerPayload {
  answers: { question_id: number; user_answer: string }[]
}
export interface ExamSwitchPayload {
  cheat_count: number
}
