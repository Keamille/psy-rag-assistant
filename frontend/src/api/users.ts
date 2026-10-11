// 用户接口（开发文档 §7.4）。
//
// 端点：读取资料、改密码、导出数据、删除数据。

import { api, http } from '@/api/client'
import type { User } from '@/api/types'

/** GET /users/me 的返回：用户资料 + 配额 + 是否管理员 */
export interface MePayload extends User {
  status: string
  consent_version: string
  consented_at: string | null
  created_at: string | null
  last_login_at: string | null
  /** 当日剩余消息配额；Redis 不可用时为 null（界面显示"未知"而不是 0） */
  quota_remaining: number | null
  is_admin: boolean
}

// GET /users/me
//
// 用途：应用启动时恢复登录状态（stores/auth.ts 的 bootstrap）。
// 这也是"数据库二次校验"的入口：用户被禁用后，即使令牌未过期，这里也会 401。
export const getMe = () => api.get<MePayload>('/users/me')

// PATCH /users/me —— 改密码，请求体 { old_password, password }
//
// 返回 { revoked_current_token, changed_at }。
// revoked_current_token 为 false 表示后端没能撤销 refresh 令牌（通常 Redis 不可用），
// 密码已经改成功了，但其他设备仍可能保持登录——界面应当提示这一点。
// 失败：401 + 2001（原密码错误）、400 + 1001（新密码太弱或与原密码相同）。
export const updatePassword = (payload: { old_password: string; password: string }) =>
  api.patch<{ revoked_current_token: boolean; changed_at: string }>('/users/me', payload)

// GET /users/me/export —— 导出全部数据（JSON 附件）
//
// 这里必须用 raw: true，因为返回的是文件流而不是统一响应体，
// 拦截器不能去拆 {code,message,data}。
export async function exportMyData(): Promise<Blob> {
  const response = await http.get<Blob>('/users/me/export', {
    responseType: 'blob',
    raw: true,
  })
  return response.data
}

// DELETE /users/me/data —— 删除会话或全部数据
// 请求体 { scope: "conversations" | "all", password }
export const deleteMyData = (payload: { scope: 'conversations' | 'all'; password: string }) =>
  api.delete<null>('/users/me/data', { data: payload })

