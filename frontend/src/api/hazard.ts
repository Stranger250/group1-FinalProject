import { cleanParams, request, uploadRequest } from './request'
import type { PageResult } from '@/types/api'
import type {
  AnalyzeResult,
  HazardCategoryNode,
  HazardCreatePayload,
  HazardDetail,
  HazardItem,
  HazardLevel,
  HazardSort,
  SortOrder,
} from '@/types/models/hazard'

/** 上传隐患图片（B03）→ {url}。业务失败由调用方判 code（如 503 视觉降级）。 */
export function uploadHazardImage(file: File) {
  const form = new FormData()
  form.append('file', file)
  return uploadRequest<{ url: string }>({ url: '/hazards/upload', method: 'POST', data: form, timeout: 30_000 })
}

/** AI 视觉识别单图（analyze）→ 建议 + detections + 多框标注图。503 由调用方降级。 */
export function analyzeHazardImage(file: File) {
  const form = new FormData()
  form.append('file', file)
  return uploadRequest<AnalyzeResult>({ url: '/hazards/analyze', method: 'POST', data: form, timeout: 300_000 })
}

/** H01 隐患上报 */
export function createHazard(payload: HazardCreatePayload) {
  return request<HazardDetail>({ url: '/hazards', method: 'POST', data: payload })
}

export interface HazardQuery {
  status?: string
  level?: HazardLevel | ''
  type?: string
  subcategory?: string
  keyword?: string
  start_time?: string
  end_time?: string
  sort?: HazardSort
  order?: SortOrder
  page?: number
  page_size?: number
}

/** H02 隐患列表（筛选 + 分页 + 排序） */
export function listHazards(params: HazardQuery) {
  return request<PageResult<HazardItem>>({ url: '/hazards', method: 'GET', params: cleanParams(params) })
}

/** H03 隐患详情 */
export function getHazard(id: number) {
  return request<HazardDetail>({ url: `/hazards/${id}`, method: 'GET' })
}

/** H03 管理员一键闭环 */
export function closeHazard(id: number) {
  return request<{ message: string; hazard_no: string; status: string }>({
    url: `/hazards/${id}/close`,
    method: 'POST',
  })
}

/** H04 派单：指定整改负责人与期限（SAFETY/ADMIN） */
export function dispatchHazard(id: number, payload: { handler_id: number; deadline?: string | null }) {
  return request<{ message: string; hazard_no: string; status: string }>({
    url: `/hazards/${id}/dispatch`,
    method: 'POST',
    data: payload,
  })
}

/** H05 整改反馈：提交整改措施与照片（负责人或 SAFETY/ADMIN） */
export function rectifyHazard(id: number, payload: { rectification_measure: string; rectification_images?: string[] }) {
  return request<{ message: string; hazard_no: string; status: string }>({
    url: `/hazards/${id}/rectify`,
    method: 'POST',
    data: payload,
  })
}

/** H06 验收：通过闭环 / 驳回（SAFETY/ADMIN） */
export function checkHazard(id: number, payload: { passed: boolean; reject_reason?: string | null }) {
  return request<{ message: string; hazard_no: string; status: string }>({
    url: `/hazards/${id}/check`,
    method: 'POST',
    data: payload,
  })
}

/** O13 安全员隐患处理（模拟实现）：标记已处理 / 驳回（SAFETY/ADMIN） */
export function auditHazard(id: number, payload: { passed: boolean; comment?: string | null }) {
  return request<{ message: string; hazard_no: string; audit_status: string }>({
    url: `/hazards/${id}/audit`,
    method: 'POST',
    data: payload,
  })
}

/** O1 隐患分类树（大类 → 子类） */
export function listHazardCategories() {
  return request<{ items: HazardCategoryNode[] }>({ url: '/hazard-categories', method: 'GET' })
}
