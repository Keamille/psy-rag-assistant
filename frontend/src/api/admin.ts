// 管理后台接口（开发文档 §7.7）。权限：admin。
//
// 四组端点：知识库文档与任务进度、参数配置、危机事件、统计。

import { api } from '@/api/client'
import type {
  AdminConfig,
  CrisisEvent,
  IngestTask,
  KnowledgeChunk,
  KnowledgeDocument,
  Paginated,
} from '@/api/types'

// ---------------------------------------------------------------------------
// 知识库文档
// ---------------------------------------------------------------------------

// GET /admin/documents —— 文档列表，支持 status / q 过滤
export const listDocuments = (params?: {
  page?: number
  size?: number
  status?: string
  q?: string
}) => api.get<Paginated<KnowledgeDocument>>('/admin/documents', { params })

// POST /admin/documents —— multipart/form-data 上传
//
// 字段：file(必填) / title / tags / sensitivity。
// 返回 202 与 { document_id, task_id, status }——后面要用 task_id 轮询进度。
//
// 文件类型与大小校验后端已经实现，所以前端不要重复拦；
// 让后端返回 400 + 1006（类型不支持）或 1001（缺 file 字段）即可，
// 这样错误信息只有一处来源。
export function uploadDocument(form: FormData) {
  return api.post<{ document_id: number; task_id: string; status: string }>(
    '/admin/documents',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
}

// GET /admin/documents/{id}/chunks —— 分块预览
export const listChunks = (documentId: number, params?: { page?: number; size?: number }) =>
  api.get<Paginated<KnowledgeChunk>>(`/admin/documents/${documentId}/chunks`, { params })

// POST /admin/documents/{id}/reindex —— 重建索引
// 会删除旧向量、重新切分并向量化，文档 version 加 1
export const reindexDocument = (documentId: number) =>
  api.post<{ task_id: string }>(`/admin/documents/${documentId}/reindex`)

// DELETE /admin/documents/{id} —— 同时清除分块与 Chroma 向量
export const deleteDocument = (documentId: number) =>
  api.delete<null>(`/admin/documents/${documentId}`)

// GET /admin/tasks/{task_id} —— 入库任务进度
//
// 文档处于 pending / processing 时，列表页应每 3 秒轮询一次，
// 进入 finished / failed 立即停止，避免无意义的请求。
export const getTask = (taskId: string) => api.get<IngestTask>(`/admin/tasks/${taskId}`)

// ---------------------------------------------------------------------------
// 参数配置
// ---------------------------------------------------------------------------

// GET /admin/config —— 返回当前生效值（只读展示）
export const getConfig = () => api.get<AdminConfig>('/admin/config')

// PUT /admin/config —— 在线改参数（写入 Redis 覆盖层）
export const updateConfig = (values: AdminConfig['values']) =>
  api.put<AdminConfig>('/admin/config', values)

// ---------------------------------------------------------------------------
// 危机事件
// ---------------------------------------------------------------------------

// GET /admin/crisis-events —— 支持 level / reviewed / follow_up_status / 时间范围过滤
export const listCrisisEvents = (params?: {
  level?: string
  reviewed?: boolean
  page?: number
  size?: number
}) => api.get<Paginated<CrisisEvent>>('/admin/crisis-events', { params })

// GET /admin/crisis-events/{id} —— 详情含脱敏片段与前后各 3 条上下文
export const getCrisisEvent = (eventId: number) =>
  api.get<CrisisEvent>(`/admin/crisis-events/${eventId}`)

// POST /admin/crisis-events/{id}/review —— 复核与回访状态
// follow_up_status 取 pending / contacted / closed；每次复核都会写审计日志
export const reviewCrisisEvent = (
  eventId: number,
  payload: { follow_up_status: string; note?: string },
) => api.post<CrisisEvent>(`/admin/crisis-events/${eventId}/review`, payload)

// ---------------------------------------------------------------------------
// 统计
// ---------------------------------------------------------------------------

// GET /admin/stats/overview?range=7d
export const getStatsOverview = (range: string) =>
  api.get<Record<string, number>>('/admin/stats/overview', { params: { range } })

