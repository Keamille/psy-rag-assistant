/** 与后端接口契约对应的类型定义（开发文档第 7 章）。 */

export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
  request_id: string
}

export interface Paginated<T> {
  items: T[]
  page: number
  size: number
  total: number
}

export interface User {
  id: number
  username: string
  email: string
  role: 'user' | 'admin'
}

export interface AuthResult {
  user: User
  access_token: string
  refresh_token: string
  expires_in: number
}

export interface Hotline {
  name: string
  phone: string
  description?: string
  priority: number
}

export interface HotlinePayload {
  region: string
  verified_at: string | null
  notice: string
  items: Hotline[]
}

export type ProbeStatus = 'ok' | 'degraded' | 'down' | 'configured' | 'unconfigured'

export interface ReadyReport {
  database: { status: ProbeStatus; latency_ms?: number; error?: string }
  redis: { status: ProbeStatus; latency_ms?: number; error?: string }
  chroma: { status: ProbeStatus; mode?: string; latency_ms?: number; error?: string }
  embedding: { status: ProbeStatus; model?: string; loaded?: boolean; error?: string }
  llm: { status: ProbeStatus; provider?: string; model?: string; error?: string }
}

export interface MetaConfig {
  disclaimer_version: string
  disclaimer_markdown: string
  max_message_length: number
  hotline_region: string
  features: Record<string, boolean>
}

export interface Conversation {
  id: number
  title: string
  status: 'active' | 'paused' | 'archived'
  crisis_level: 'medium' | 'high' | null
  message_count: number
  created_at: string
  updated_at: string
}

/** 引用来源（对应 SSE sources 事件，开发文档 7.2 / 8.8） */
export interface SourceItem {
  index: number
  document_title: string
  section_path: string
  page: number | null
  snippet: string
  score: number | null
}

export interface CrisisCardPayload {
  level: 'medium' | 'high'
  source: 'rule' | 'model' | 'both'
  matched_terms: string[]
  action: 'interrupt' | 'warned_and_continued'
  card: { title: string; body: string; confirm_text: string } | null
  hotlines: Hotline[]
}

export type MessageRole = 'user' | 'assistant' | 'system_card'

/** 知识库文档（对应 GET /admin/documents 的列表项） */
export interface KnowledgeDocument {
  id: number
  title: string
  source_type: 'pdf' | 'docx' | 'md' | 'txt' | 'builtin'
  filename: string | null
  status: 'pending' | 'processing' | 'ready' | 'failed'
  error_message: string | null
  chunk_count: number
  version: number
  is_builtin: boolean
  created_at: string
}

/** 知识库分块（对应 GET /admin/documents/{id}/chunks） */
export interface KnowledgeChunk {
  id: number
  document_id: number
  seq: number
  content: string
  section_path: string | null
  page: number | null
  token_count: number | null
  chroma_id: string
  is_active: boolean
}

/** 危机事件（对应 GET /admin/crisis-events） */
export interface CrisisEvent {
  id: number
  user_id: number
  conversation_id: number
  message_id: number | null
  level: 'medium' | 'high'
  source: 'rule' | 'model' | 'both'
  matched_terms: string | null
  action_taken: 'interrupted' | 'warned_and_continued'
  reviewed: boolean
  reviewed_at: string | null
  follow_up_status: 'pending' | 'contacted' | 'closed' | null
  review_note: string | null
  snippet: string | null
  created_at: string
}

/** 后台可调参数（对应 GET|PUT /admin/config） */
export interface AdminConfig {
  values: {
    top_k_retrieve: number
    top_k_rerank: number
    rerank_enabled: boolean
    llm_temperature: number
    llm_max_tokens: number
    daily_message_quota: number
    hotline_region: string
  }
  source: string
  editable_keys: string[]
  restart_required_keys: string[]
}

/** 任务进度（对应 GET /admin/tasks/{task_id}） */
export interface IngestTask {
  task_id: string
  status: 'queued' | 'running' | 'finished' | 'failed'
  progress: number
  stage: string
  detail: Record<string, number>
  error: string | null
}

export interface ChatMessage {
  id: number | string
  role: MessageRole
  content: string
  created_at: string
  risk_level?: 'safe' | 'medium' | 'high' | null
  sources?: SourceItem[]
  streaming?: boolean
  error?: { code: number; message: string; retryable?: boolean } | null
  crisis?: CrisisCardPayload | null
  client_msg_id?: string
}

