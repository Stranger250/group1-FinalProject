/** O8 用户端考试工坊 API（/my-papers、/shared-papers、/users/search）。 */
import { downloadRequest, request } from './request'
import type { PageResult } from '@/types/api'
import type { SharedPaperItem, UserPaperItem, WorkshopPaperBrief } from '@/types/models/workshop'

/** 我的试卷列表 */
export function listMyPapers(params: { page?: number; page_size?: number }) {
  return request<PageResult<UserPaperItem>>({ url: '/my-papers', method: 'GET', params })
}

/** 手动组卷 */
export function createMyPaper(payload: {
  name: string
  duration: 30 | 60 | 90
  pass_score: number
  total_score: number
  questions: { question_id: number; score?: number | null }[]
}) {
  return request<WorkshopPaperBrief>({ url: '/my-papers', method: 'POST', data: payload })
}

/** 删除试卷（仅草稿） */
export function deleteMyPaper(pid: number) {
  return request<{ message: string }>({ url: `/my-papers/${pid}`, method: 'DELETE' })
}

/** 发布考试给指定用户 */
export function publishMyPaper(pid: number, payload: { target_user_ids: number[] }) {
  return request<{ message: string; status: string; targets: number[] }>({
    url: `/my-papers/${pid}/publish`, method: 'POST', data: payload,
  })
}

/** 发布列表 */
export function listPaperShares(pid: number) {
  return request<{ items: { target_user_id: number; target_name: string; status: string; create_time: string | null }[] }>({
    url: `/my-papers/${pid}/shares`, method: 'GET',
  })
}

/** 撤销发布 */
export function revokeMyShare(pid: number, targetUserId: number) {
  return request<{ message: string }>({ url: `/my-papers/${pid}/shares/${targetUserId}`, method: 'DELETE' })
}

/** 导出 Word（返回 blob） */
export function exportPaperWord(pid: number, withAnswers: boolean) {
  return downloadRequest(`/my-papers/${pid}/export-word?answers=${withAnswers ? 1 : 0}`)
}

/** 分享给我的 */
export function listSharedPapers(params: { page?: number; page_size?: number }) {
  return request<PageResult<SharedPaperItem>>({ url: '/shared-papers', method: 'GET', params })
}

/** 收藏副本 */
export function copySharedPaper(pid: number) {
  return request<WorkshopPaperBrief>({ url: `/shared-papers/${pid}/copy`, method: 'POST' })
}

/** 搜索目标用户（发布考试选择，排除自己） */
export function searchTargetUsers(keyword: string) {
  return request<{ items: { id: number; name: string; username: string; role_id: number }[] }>({
    url: '/users/search', method: 'GET', params: { keyword },
  })
}
