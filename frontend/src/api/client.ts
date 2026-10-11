// axios 封装（开发文档 §6.3 / §7.1）。
//
// 约定：
//   - 后端统一返回 {code, message, data, request_id}
//   - 拦截器直接把 data 拆出来返回，业务代码拿到的就是纯数据
//   - code !== 0 一律抛 ApiError
//   - 401 + 1002 时静默续期一次并重放原请求；续期也失败才跳登录
//
// 注意：这个文件属于基础设施，不属于"前后端串联"那一层。

import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'

import { refreshAccessToken, tokenStore } from '@/api/token'
import type { ApiEnvelope } from '@/api/types'

declare module 'axios' {
  export interface AxiosRequestConfig {
    // 置为 true 时响应拦截器不做 {code,message,data} 拆包。
    // 用于下载文件这类不是统一响应体的接口（例如导出我的数据）。
    raw?: boolean
  }
}

/** 业务错误。携带后端的业务码与 HTTP 状态，便于调用方分流处理。 */
export class ApiError extends Error {
  code: number
  httpStatus: number
  requestId?: string
  /** 结构化附加信息。目前只有限流会带：{ retry_after: 37 } */
  data?: Record<string, unknown> | null

  constructor(
    code: number,
    message: string,
    httpStatus: number,
    requestId?: string,
    data?: Record<string, unknown> | null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.httpStatus = httpStatus
    this.requestId = requestId
    this.data = data ?? null
  }

  /** 限流（429 + 1005）。retryAfter 是后端告知的等待秒数。 */
  get isRateLimited(): boolean {
    return this.code === 1005
  }

  get retryAfter(): number | null {
    const value = this.data?.retry_after
    return typeof value === 'number' && value > 0 ? value : null
  }

  /** 认证失效，通常意味着需要重新登录 */
  get isUnauthorized(): boolean {
    return this.code === 1002 || this.httpStatus === 401
  }
}

const baseURL = import.meta.env.VITE_API_BASE ?? '/api/v1'

export const http: AxiosInstance = axios.create({
  baseURL,
  timeout: 20000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  const token = tokenStore.access
  // 只在调用方没有显式指定 Authorization 时才自动带上访问令牌。
  // /auth/logout 需要携带的是 refresh 令牌，它会自己指定这个头。
  if (token && !config.headers?.Authorization) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

function onUnauthorized(): void {
  tokenStore.clear()
  // 拦截器里拿不到 router（会形成循环依赖），改用事件通知
  window.dispatchEvent(new CustomEvent('psy:unauthorized'))
}

http.interceptors.response.use(
  (response) => {
    // 文件下载等场景需要拿到完整的 response
    if (response.config?.raw) return response as never
    return response.data?.data as never
  },

  async (error) => {
    const response = error?.response
    const payload = response?.data as ApiEnvelope<unknown> | undefined

    // 访问令牌过期：静默续期一次，成功后重放原请求
    if (response?.status === 401 && payload?.code === 1002 && !error.config?.__retried) {
      error.config.__retried = true
      const access = await refreshAccessToken()
      if (access) {
        error.config.headers = error.config.headers ?? {}
        error.config.headers.Authorization = `Bearer ${access}`
        return http.request(error.config)
      }
      onUnauthorized()
    }

    if (payload && typeof payload.code === 'number') {
      throw new ApiError(
        payload.code,
        payload.message,
        response.status,
        payload.request_id,
        payload.data as Record<string, unknown> | null,
      )
    }
    throw new ApiError(9001, error?.message ?? '网络异常', response?.status ?? 0)
  },
)

export const api = {
  get: <T>(url: string, config?: AxiosRequestConfig) => http.get(url, config) as Promise<T>,
  post: <T>(url: string, body?: unknown, config?: AxiosRequestConfig) =>
    http.post(url, body, config) as Promise<T>,
  patch: <T>(url: string, body?: unknown, config?: AxiosRequestConfig) =>
    http.patch(url, body, config) as Promise<T>,
  put: <T>(url: string, body?: unknown, config?: AxiosRequestConfig) =>
    http.put(url, body, config) as Promise<T>,
  delete: <T>(url: string, config?: AxiosRequestConfig) => http.delete(url, config) as Promise<T>,
}

