// 认证接口（开发文档 §7.3）。
//
// 分层约定：本文件只负责"发请求、返回数据"，**不碰令牌存储**。
// 令牌的写入与清空由 stores/auth.ts 统一处理——因为注销失败时
// （Redis 不可用返回 503）必须保留本地令牌，这个判断属于状态管理，不属于传输层。
//
// 刷新令牌的实现放在 api/token.ts，原因见那个文件顶部的说明。

import { api } from '@/api/client'
import { tokenStore } from '@/api/token'
import type { AuthResult } from '@/api/types'

export interface LoginPayload {
  /** 用户名或邮箱，后端自行判断走哪个字段 */
  account: string
  password: string
}

export interface RegisterPayload {
  email: string
  username: string
  password: string
  age_confirmed: boolean
  consent: boolean
  /** 必须来自 GET /meta/config 的 disclaimer_version，不要写死 */
  consent_version: string
}

// POST /auth/login
// 返回 { user, access_token, refresh_token, expires_in }
// 失败：401 + 2001（账号或密码错误）、403（账号已被禁用）
export const login = (payload: LoginPayload) => api.post<AuthResult>('/auth/login', payload)

// POST /auth/register —— 注册即登录，返回结构与登录一致
// 失败：400 + 1001（参数校验）、409 + 2002（邮箱或用户名已存在）
export const register = (payload: RegisterPayload) => api.post<AuthResult>('/auth/register', payload)

// POST /auth/logout —— 把 refresh 令牌加入黑名单
//
// 注意：这个端点要求的是 **refresh** 令牌，不是访问令牌。
// 所以要显式指定 Authorization 头覆盖掉请求拦截器的默认行为。
//
// 调用方要注意：返回 503（Redis 不可用）时说明撤销失败，
// 此时**不能**清空本地令牌，否则用户以为已退出、令牌其实还有效。
export const logout = () => {
  const refresh = tokenStore.refresh
  if (!refresh) return Promise.resolve(null)
  return api.post<null>('/auth/logout', undefined, {
    headers: { Authorization: `Bearer ${refresh}` },
  })
}

