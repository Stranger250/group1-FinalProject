import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import type { ApiResponse } from '@/types/api'

/** 统一提示文案（FRONTEND.md C10） */
export const NOT_FOUND_MSG = '请求的资源不存在'
export const FORBIDDEN_MSG = '无权限访问该接口'

/** 业务错误（后端 {code,message} 中 code !== 200） */
export class ApiError extends Error {
  code: number
  constructor(code: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

/** 401 处理回调（由 main.ts 注册，避免本文件与 store/router 循环依赖） */
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn
}

const instance = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
})

instance.interceptors.request.use((config) => {
  const token = localStorage.getItem('shudao_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/** 从错误体中取文案：优先后端 {message}，兼容 Starlette {detail} */
function errMessage(data: unknown, fallback: string): string {
  const d = data as { message?: string; detail?: string } | null
  return d?.message ?? d?.detail ?? fallback
}

instance.interceptors.response.use(
  (res) => res,
  (error: AxiosError<unknown>) => {
    const status = error.response?.status
    const body = error.response?.data
    if (status === 401) {
      localStorage.removeItem('shudao_token')
      onUnauthorized?.()
    } else {
      const fallback =
        status === 403
          ? FORBIDDEN_MSG
          : status === 404
            ? NOT_FOUND_MSG
            : status === 502
              ? 'AI 服务异常，请稍后重试'
              : status === 503
                ? '服务暂不可用，请稍后重试'
                : '网络异常，请稍后重试'
      ElMessage.error(errMessage(body, fallback))
    }
    return Promise.reject(error)
  },
)

/**
 * 普通请求：解包 {code,message,data}，code!==200 抛 ApiError（并全局提示）。
 * @returns data（已解包）
 */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const res = await instance.request<ApiResponse<T>>(config)
  const body = res.data
  if (body.code !== 200) {
    ElMessage.error(body.message || '请求失败')
    throw new ApiError(body.code, body.message)
  }
  return body.data
}

/**
 * 上传/AI 识别专用：返回原样 ApiResponse，业务失败（如 503 视觉降级）由调用方判断 code。
 * 适用于需要拿到 503 降级信息做「可跳过」引导的接口。
 */
export async function uploadRequest<T>(config: AxiosRequestConfig): Promise<ApiResponse<T>> {
  const res = await instance.request<ApiResponse<T>>(config)
  return res.data
}

/** 过滤 params 中的空值（undefined/null/''），避免向后端发送多余空参数 */
export function cleanParams(params: object): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    out[k] = v
  }
  return out
}
