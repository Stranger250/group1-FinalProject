/** 后端统一响应与分页结构（FRONTEND.md §4）。 */

/** 统一响应 {code, message, data}；code===200 为成功 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 后端分页结构：page/page_size/total/items */
export interface PageResult<T> {
  page: number
  page_size: number
  total: number
  items: T[]
}
