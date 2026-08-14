import { cleanParams, request } from './request'
import type { PageResult } from '@/types/api'
import type { UserAdminItem, UserUpdatePayload } from '@/types/models/user'

/** 用户列表查询参数（管理端） */
export interface UserQuery {
  keyword?: string
  role_id?: number
  status?: number
  page?: number
  page_size?: number
}

/** 管理端：用户列表（分页 + 关键字 + 角色 + 状态筛选） */
export function listUsers(params: UserQuery) {
  return request<PageResult<UserAdminItem>>({ url: '/users', method: 'GET', params: cleanParams(params) })
}

/** 管理端：更新用户（改角色 / 启用禁用） */
export function updateUser(id: number, payload: UserUpdatePayload) {
  return request<UserAdminItem>({ url: `/users/${id}`, method: 'PUT', data: payload })
}

/** 管理端：重置密码（返回一次性临时密码） */
export function resetUserPassword(id: number) {
  return request<{ username: string; new_password: string }>({
    url: `/users/${id}/reset-password`,
    method: 'POST',
  })
}
