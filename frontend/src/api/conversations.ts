// 会话与消息接口（开发文档 §7.5 / §7.6）。
//

import { api } from '@/api/client'
import { postSSE, type SSEHandlers } from '@/composables/useSSE'
import type { ChatMessage, Conversation, Paginated } from '@/api/types'

// GET /conversations —— 会话列表
//
// 后端按 updated_at 倒序返回，前端不要再重排。
export const listConversations = (params?: { page?: number; size?: number; status?: string }) =>
  api.get<Paginated<Conversation>>('/conversations', { params })

// POST /conversations —— 新建会话，请求体可选 { title }
export const createConversation = (title?: string) =>
  api.post<Conversation>('/conversations', title ? { title } : {})

// GET /conversations/{id}
export const getConversation = (id: number) => api.get<Conversation>(`/conversations/${id}`)

// PATCH /conversations/{id} —— 请求体可含 { title, status }
// status 取 active / archived
export const updateConversation = (id: number, payload: { title?: string; status?: string }) =>
  api.patch<Conversation>(`/conversations/${id}`, payload)

// DELETE /conversations/{id} —— 后端是软删除（写 deleted_at），不是物理删除
export const deleteConversation = (id: number) => api.delete<null>(`/conversations/${id}`)

// GET /conversations/{id}/messages —— 消息列表（后端按时间倒序返回）
export const listMessages = (conversationId: number, params?: { page?: number; size?: number }) =>
  api.get<Paginated<ChatMessage>>(`/conversations/${conversationId}/messages`, { params })

// POST /conversations/{id}/messages —— SSE 流式对话
//
// 这里不能走 axios：返回的是 text/event-stream 事件流，不是 JSON。
// postSSE 用 fetch + ReadableStream 手动解析，事件序为：
//   meta → risk? → delta* → sources → done / error
//
// 三个关键边界都在 stores/chat.ts 里处理：
//   风险中断只发 risk + done，不产生任何 delta；
//   断流（没收到 done 就断开）时只给"重新生成"按钮，不自动重试；
//   限流 429 时 err.data.retry_after 是要等的秒数。
export function sendMessage(
  conversationId: number,
  payload: { text: string; client_msg_id: string },
  handlers: SSEHandlers,
  signal: AbortSignal,
): Promise<void> {
  return postSSE(`/conversations/${conversationId}/messages`, payload, handlers, signal)
}

// POST /conversations/{id}/resume —— 危机中断后解锁会话
// 请求体固定为 { confirm: "i_am_safe" }；后端会把这次操作写进审计日志
export const resumeConversation = (id: number) =>
  api.post<Conversation>(`/conversations/${id}/resume`, { confirm: 'i_am_safe' })

