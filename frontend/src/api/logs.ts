import { cleanParams, request } from './request'
import type { PageResult } from '@/types/api'

/** 审计日志条目 */
export interface AuditLogItem {
  id: number
  user_id: number
  username: string | null
  action: string
  target_type: string | null
  target_id: string | null
  detail: string | null
  ip: string | null
  create_time: string | null
}

/** 审计日志列表（ADMIN） */
export function listAuditLogs(params: {
  action?: string
  keyword?: string
  start_time?: string
  end_time?: string
  page?: number
  page_size?: number
}) {
  return request<PageResult<AuditLogItem>>({ url: '/logs', method: 'GET', params: cleanParams(params) })
}

/** 动作中文标签 */
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  login: '登录成功',
  login_failed: '登录失败',
  login_disabled: '登录被拒（账号禁用）',
  register: '注册',
  password_reset: '重置密码',
  user_update: '用户变更',
  hazard_close: '隐患闭环',
  hazard_dispatch: '隐患派单',
  hazard_rectify: '隐患整改',
  hazard_check: '隐患验收',
  question_create: '题目新增',
  question_update: '题目编辑',
  question_delete: '题目删除',
  question_import: '题目批量导入',
  question_review: '题目审核',
  ai_generate: 'AI 出题',
  paper_status: '试卷状态变更',
  exam_submit: '考试交卷',
}

export function auditActionLabel(action: string): string {
  return AUDIT_ACTION_LABELS[action] ?? action
}
