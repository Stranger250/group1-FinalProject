import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { loginApi, meApi, registerApi } from '@/api/auth'
import type { RegisterPayload, UserInfo } from '@/types/models/user'

const TOKEN_KEY = 'shudao_token'

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) ?? '')
  const user = ref<UserInfo | null>(null)

  const isLoggedIn = computed(() => !!token.value)
  const roleId = computed(() => user.value?.role_id ?? 0)

  function setSession(t: string, u: UserInfo): void {
    token.value = t
    user.value = u
    localStorage.setItem(TOKEN_KEY, t)
  }

  /** 登录：成功后持久化 token + user */
  async function login(username: string, password: string): Promise<UserInfo> {
    const data = await loginApi(username, password)
    setSession(data.access_token, data.user)
    return data.user
  }

  /** 注册：返回用户信息（不自动登录，由页面回填登录表单） */
  function register(payload: RegisterPayload) {
    return registerApi(payload)
  }

  /** 会话恢复：刷新页面后拉取 /me */
  async function fetchMe(): Promise<UserInfo> {
    const me = await meApi()
    user.value = me
    return me
  }

  /** 个人中心保存资料/头像后，同步本地 user（HeaderBar 等实时反映） */
  function setUser(u: UserInfo): void {
    user.value = u
  }

  function logout(): void {
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
  }

  return { token, user, isLoggedIn, roleId, login, register, fetchMe, setUser, logout }
})
