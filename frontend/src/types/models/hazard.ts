/** 模块一 隐患安全管理模型（对齐 /api/v1/hazards/* 契约）。 */

export type HazardLevel = 'CRITICAL' | 'MAJOR' | 'GENERAL' | 'MINOR'
export type HazardStatus = 'WAIT_PROCESS' | 'PROCESSING' | 'WAIT_CHECK' | 'FINISHED' | 'REJECTED'

/** O13 安全员隐患处理状态（模拟实现） */
export type HazardAuditStatus = 'pending' | 'approved' | 'rejected'

/** 归一化 bbox：[x1, y1, x2, y2]，0~1 */
export type BBox = [number, number, number, number]

/** 单处隐患检测（AI 识别 detections 元素） */
export interface HazardDetection {
  type: string
  level: string
  description: string
  reason: string
  confidence: number
  bbox: BBox | null
  /** 兼容旧版 risk_report（老数据用 type_suggest/level_suggest 字段名） */
  type_suggest?: string
  level_suggest?: string
}

/** 隐患图片行 */
export interface HazardImage {
  id: number
  image_url: string
  uploader_id: number
  create_time: string | null
}

/** 处理进度时间线节点 */
export interface HazardLogItem {
  id: number
  operation: string
  operator_id: number
  operator_name: string
  old_status: string | null
  new_status: string | null
  remark: string | null
  create_time: string | null
}

/** 列表行（HazardService._item） */
export interface HazardItem {
  id: number
  hazard_no: string
  title: string
  description: string
  location: string
  level: HazardLevel
  type: string
  status: HazardStatus
  creator_id: number
  creator_name: string
  reporter_name: string
  audit_status: HazardAuditStatus
  image_count: number
  create_time: string | null
  update_time: string | null
}

/** 详情（HazardService._detail） */
export interface HazardDetail {
  id: number
  hazard_no: string
  title: string
  description: string
  location: string
  level: HazardLevel
  type: string
  status: HazardStatus
  creator_id: number
  creator_name: string
  reporter_name: string
  handler_id: number | null
  deadline: string | null
  rectification_measure: string | null
  rectification_images: string | null
  reject_reason: string | null
  risk_report: Record<string, unknown> | null
  audit_status: HazardAuditStatus
  audit_by: number | null
  audit_at: string | null
  audit_comment: string | null
  images: HazardImage[]
  timeline: HazardLogItem[]
  create_time: string | null
  update_time: string | null
}

/** H01 上报请求体（HazardCreate） */
export interface HazardCreatePayload {
  title?: string
  description: string
  location?: string
  level: HazardLevel
  type?: string
  reporter_name?: string
  images: string[]
  risk_report?: Record<string, unknown> | null
}

/** POST /hazards/analyze 识别结果 */
export interface AnalyzeResult {
  url: string
  type_suggest: string
  level_suggest: HazardLevel
  description: string
  reason: string
  confidence: number
  bbox: BBox | null
  detections: HazardDetection[]
  annotated_url: string | null
  report: Record<string, unknown>
}

/** H02 列表排序参数（R1 后端配套） */
export type HazardSort = 'create_time' | 'level'
export type SortOrder = 'asc' | 'desc'
