import { request } from './request'
import type {
  ChangePasswordPayload,
  LoginResult,
  ProfileUpdatePayload,
  RegisterPayload,
  UserInfo,
} from '@/types/models/user'

/** 登录：OAuth2 密码模式，body 必须为 form-urlencoded（非 JSON） */
export function loginApi(username: string, password: string) {
  const form = new URLSearchParams()
  form.append('username', username)
  form.append('password', password)
  return request<LoginResult>({
    url: '/auth/login',
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: form.toString(),
  })
}

/** 注册：返回用户信息（不自动登录） */
export function registerApi(payload: RegisterPayload) {
  return request<UserInfo>({ url: '/auth/register', method: 'POST', data: payload })
}

/** 当前用户信息（会话恢复） */
export function meApi() {
  return request<UserInfo>({ url: '/auth/me', method: 'GET' })
}

/** 个人中心：修改资料（姓名/手机号/邮箱） */
export function updateProfileApi(payload: ProfileUpdatePayload) {
  return request<UserInfo>({ url: '/auth/profile', method: 'PUT', data: payload })
}

/** 个人中心：修改密码（校验原密码） */
export function changePasswordApi(payload: ChangePasswordPayload) {
  return request<{ message?: string }>({ url: '/auth/password', method: 'PUT', data: payload })
}

/** 个人中心：上传头像（jpg/png/jpeg）→ 更新后的用户资料 */
export function uploadAvatarApi(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<UserInfo>({ url: '/auth/avatar', method: 'POST', data: form, timeout: 30_000 })
}
