// 令牌基础设施：存储 + 刷新。
//
// 为什么刷新逻辑放在这里，而不是放在 api/auth.ts：
// client.ts 的响应拦截器需要在 401 时自动续期，而 auth.ts 又需要 client.ts 的
// axios 实例去调登录接口。如果把 refresh 放在 auth.ts，两者就形成循环依赖。
// token.ts 不依赖 client.ts，放在这里两边都能用，且不会重复实现。

import axios from 'axios'

import type { ApiEnvelope } from '@/api/types'

const ACCESS_KEY = 'psy_access_token'
const REFRESH_KEY = 'psy_refresh_token'

const baseURL = import.meta.env.VITE_API_BASE ?? '/api/v1'

export const tokenStore = {
  get access(): string | null {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh(): string | null {
    return localStorage.getItem(REFRESH_KEY)
  },
  set(access: string, refresh?: string): void {
    localStorage.setItem(ACCESS_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear(): void {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

// 裸 axios 实例：不带拦截器，避免"刷新失败 → 触发拦截器 → 又去刷新"的递归
const raw = axios.create({ baseURL, timeout: 20000 })

let inflight: Promise<string | null> | null = null

// 用 refresh 令牌换新的 access 令牌。
//
// 并发场景下多个请求可能同时收到 401，这里用 inflight 去重：
// 同一时刻只发一次刷新请求，其余请求等待同一个 Promise。
// 否则会连续签发多枚令牌，并把其中几枚立即作废。
export function refreshAccessToken(): Promise<string | null> {
  if (inflight) return inflight

  const refreshToken = tokenStore.refresh
  if (!refreshToken) return Promise.resolve(null)

  inflight = raw
    .post<ApiEnvelope<{ access_token: string; expires_in: number }>>(
      '/auth/refresh',
      {},
      // 关键：这里放的是 refresh 令牌，不是 access 令牌
      { headers: { Authorization: `Bearer ${refreshToken}` } },
    )
    .then((resp) => {
      const access = resp.data?.data?.access_token
      if (!access) return null
      tokenStore.set(access)
      return access
    })
    .catch(() => null)
    .finally(() => {
      inflight = null
    })

  return inflight
}

