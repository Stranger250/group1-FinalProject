/** 用户与认证模型（对齐 /api/v1/auth/* 契约）。 */

export interface UserInfo {
  id: number
  username: string
  name: string
  role_id: number
  phone: string | null
  email?: string | null
  avatar?: string | null
  created_time?: string
  updated_time?: string
}

export interface LoginResult {
  access_token: string
  token_type: string
  user: UserInfo
}

export interface RegisterPayload {
  username: string
  password: string
  name: string
  phone?: string
}

/** 个人中心：修改资料（姓名必填，手机号/邮箱选填） */
export interface ProfileUpdatePayload {
  name: string
  phone?: string | null
  email?: string | null
}

/** 个人中心：修改密码 */
export interface ChangePasswordPayload {
  old_password: string
  new_password: string
}

/** 管理端用户列表项（/api/v1/users，含 status） */
export interface UserAdminItem {
  id: number
  username: string
  name: string
  role_id: number
  phone: string | null
  email?: string | null
  avatar?: string | null
  status: number
  created_time?: string
  updated_time?: string
}

/** 管理端更新用户（角色/状态至少其一） */
export interface UserUpdatePayload {
  role_id?: number
  status?: number
}

/** 角色枚举（user.role_id）：1=普通员工 2=安全管理员 3=系统管理员 */
export const ROLE = { EMPLOYEE: 1, SAFETY: 2, ADMIN: 3 } as const

/** 角色中文名（header 展示 / 表格列） */
export function roleName(roleId: number): string {
  if (roleId === ROLE.ADMIN) return '系统管理员'
  if (roleId === ROLE.SAFETY) return '安全管理员'
  return '普通员工'
}
