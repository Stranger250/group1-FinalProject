import { cleanParams, request, uploadRequest } from './request'
import type { PageResult } from '@/types/api'
import type {
  AnalyzeResult,
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
