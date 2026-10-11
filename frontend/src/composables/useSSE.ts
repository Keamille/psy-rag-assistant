// SSE 客户端（开发文档 §7.2 / §11.5）。
//
// 为什么不用原生 EventSource：
//   1. 它无法携带 Authorization 头，而本项目的接口都需要鉴权；
//   2. 它只支持 GET，而发消息必须用 POST 带 body。
// 因此这里用 fetch + ReadableStream 手动解析事件流。
//
// 另一个副作用：不走 axios 就意味着 client.ts 的 401 静默续期拦截器帮不到它，
// 所以本文件自己实现了一次续期重试（见 postSSE 里的 refreshAccessToken）。

import { refreshAccessToken, tokenStore } from '@/api/token'
import type { CrisisCardPayload, SourceItem } from '@/api/types'

export interface SSEError {
  code: number
  message: string
  retryable?: boolean
  /** 限流时后端告知的等待秒数（来自 429 响应的 data.retry_after） */
  retryAfter?: number
}

export interface SSEHandlers {
  onMeta?: (d: {
    conversation_id: number
    user_message_id: number
    client_msg_id?: string
  }) => void
  onRisk?: (d: CrisisCardPayload) => void
  onDelta?: (text: string) => void
  onSources?: (items: SourceItem[]) => void
  onDone?: (d: {
    assistant_message_id: number
    finish_reason: string
    usage: { prompt_tokens: number; completion_tokens: number } | null
    latency_ms: number
  }) => void
  onError?: (e: SSEError) => void
}

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'

// 发起 SSE 请求。流正常结束或出错后 resolve（不抛异常，错误走 onError）。
// 通过 AbortSignal 支持"停止生成"。
export async function postSSE(
  path: string,
  body: unknown,
  handlers: SSEHandlers,
  signal: AbortSignal,
): Promise<void> {
  let resp = await doFetch(path, body, signal, handlers)

  // 访问令牌过期：续期一次后重放。SSE 不走 axios，拦截器的自动续期帮不到这里。
  if (resp && resp.status === 401 && !signal.aborted) {
    const access = await refreshAccessToken()
    if (access) {
      resp = await doFetch(path, body, signal, handlers)
    }
  }

  if (!resp) return // 已中止，或网络异常时 doFetch 已经报过了

  // 必须按内容类型判断：接口出错时返回的是 JSON 而不是事件流。
  // 不判断的话前端会一直等一个永远不会来的流，表现为无限转圈。
  const contentType = resp.headers.get('Content-Type') ?? ''
  if (!resp.ok || !contentType.includes('text/event-stream')) {
    await reportHttpError(resp, handlers)
    return
  }

  const reader = resp.body?.getReader()
  if (!reader) {
    handlers.onError?.({ code: 9001, message: '响应流不可读', retryable: true })
    return
  }

  await readStream(reader, handlers)
}

async function doFetch(
  path: string,
  body: unknown,
  signal: AbortSignal,
  handlers: SSEHandlers,
): Promise<Response | null> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  const token = tokenStore.access
  if (token) headers.Authorization = `Bearer ${token}`

  try {
    return await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal,
    })
  } catch (err) {
    // 用户主动中止不是错误，不要弹错误提示
    if ((err as Error).name === 'AbortError') return null
    handlers.onError?.({ code: 9001, message: '网络异常，请稍后重试', retryable: true })
    return null
  }
}

async function reportHttpError(resp: Response, handlers: SSEHandlers): Promise<void> {
  const payload = await resp.json().catch(() => null)
  const retryAfter = payload?.data?.retry_after
  handlers.onError?.({
    code: payload?.code ?? 9001,
    message: payload?.message ?? '请求失败',
    retryable: resp.status >= 500,
    retryAfter: typeof retryAfter === 'number' ? retryAfter : undefined,
  })
}

async function readStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  handlers: SSEHandlers,
): Promise<void> {
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 以空行分隔事件；兼容 \n\n 与 \r\n\r\n
      let sep = buffer.search(/\r?\n\r?\n/)
      while (sep !== -1) {
        const raw = buffer.slice(0, sep)
        buffer = buffer.slice(sep).replace(/^\r?\n\r?\n/, '')
        dispatch(raw, handlers)
        sep = buffer.search(/\r?\n\r?\n/)
      }
    }
  } catch (err) {
    if ((err as Error).name !== 'AbortError') {
      // 断流：没收到 done 就断开。给"重新生成"按钮，不自动重试——
      // 自动重试会造成重复消息与重复计费。
      handlers.onError?.({ code: 9001, message: '连接中断，可点击重新生成', retryable: true })
    }
  }
}

function dispatch(raw: string, handlers: SSEHandlers): void {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith(':')) continue // keep-alive 注释行
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (dataLines.length === 0) return

  let payload: any
  try {
    payload = JSON.parse(dataLines.join('\n'))
  } catch {
    return
  }

  switch (event) {
    case 'meta':
      handlers.onMeta?.(payload)
      break
    case 'risk':
      handlers.onRisk?.(payload)
      break
    case 'delta':
      handlers.onDelta?.(payload.text ?? '')
      break
    case 'sources':
      handlers.onSources?.(payload.items ?? [])
      break
    case 'done':
      handlers.onDone?.(payload)
      break
    case 'error':
      handlers.onError?.(payload)
      break
    default:
      break
  }
}

