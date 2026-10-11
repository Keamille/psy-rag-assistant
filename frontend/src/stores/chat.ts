// 单轮对话的流式状态。
//
// 事件协议的六个分支（meta / risk / delta / sources / done / error）都在这里落位，
// 与开发文档 §7.2 一一对应。

import { ref } from 'vue'
import { defineStore } from 'pinia'

import * as conversationApi from '@/api/conversations'
import { ApiError } from '@/api/client'
import type { ChatMessage, CrisisCardPayload, SourceItem } from '@/api/types'
import type { SSEError } from '@/composables/useSSE'
import { useConversationStore } from '@/stores/conversation'

function makeClientMsgId(): string {
  return `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export const useChatStore = defineStore('chat', () => {
  const streaming = ref(false)
  const controller = ref<AbortController | null>(null)
  const crisis = ref<CrisisCardPayload | null>(null)
  const lastError = ref<SSEError | null>(null)
  /** 限流解禁时间戳（毫秒）。ChatInput 据此倒计时。 */
  const rateLimitedUntil = ref<number | null>(null)

  function clearRateLimit(): void {
    rateLimitedUntil.value = null
  }

  // 触发一次流式生成。appendUserMessage 为 false 时用于"重新生成"，
  // 此时用户消息已经在列表里，不要重复插入。
  async function streamReply(
    conversationId: number,
    text: string,
    clientMsgId: string,
  ): Promise<void> {
    const conversation = useConversationStore()

    const placeholderId = `pending-${clientMsgId}-${Date.now().toString(36)}`
    conversation.appendMessage(conversationId, {
      id: placeholderId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      streaming: true,
      sources: [],
    })

    streaming.value = true
    lastError.value = null
    crisis.value = null

    const abort = new AbortController()
    controller.value = abort

    let buffer = ''
    let sources: SourceItem[] = []

    const handlers = {
      onMeta: (meta: { user_message_id: number }) => {
        conversation.updateMessage(conversationId, clientMsgId, { id: meta.user_message_id })
      },
      onRisk: (payload: CrisisCardPayload) => {
        crisis.value = payload
        conversation.updateMessage(conversationId, placeholderId, { crisis: payload })
      },
      onDelta: (chunk: string) => {
        buffer += chunk
        conversation.updateMessage(conversationId, placeholderId, { content: buffer })
      },
      onSources: (items: SourceItem[]) => {
        sources = items
        conversation.updateMessage(conversationId, placeholderId, { sources: items })
      },
      onDone: (done: { assistant_message_id: number }) => {
        conversation.updateMessage(conversationId, placeholderId, {
          id: done.assistant_message_id,
          content: buffer,
          sources,
          streaming: false,
        })
      },
      onError: (err: SSEError) => {
        lastError.value = err
        if (err.code === 1005) {
          // 限流：后端在 data.retry_after 里告知还要等多久
          rateLimitedUntil.value = Date.now() + (err.retryAfter ?? 60) * 1000
        }
        conversation.updateMessage(conversationId, placeholderId, {
          streaming: false,
          error: err,
          content: buffer,
        })
      },
    }

    try {
      await conversationApi.sendMessage(
        conversationId,
        { text, client_msg_id: clientMsgId },
        handlers,
        abort.signal,
      )
    } catch (err) {
      // 兜底：sendMessage 正常不会抛，但意外情况要能落到界面上
      handlers.onError({
        code: err instanceof ApiError ? err.code : 9001,
        message: err instanceof Error ? err.message : '发送失败',
        retryable: true,
      })
    } finally {
      streaming.value = false
      controller.value = null
    }
  }

  async function send(conversationId: number, text: string): Promise<void> {
    const conversation = useConversationStore()
    const clientMsgId = makeClientMsgId()

    // 乐观插入用户消息：先上屏，失败也不回滚（用户至少能看到自己说了什么）
    conversation.appendMessage(conversationId, {
      id: clientMsgId,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
      client_msg_id: clientMsgId,
    })

    await streamReply(conversationId, text, clientMsgId)
  }

  // 重新生成。
  //
  // 用于两种场景：生成失败（4001/4002）与断流。做法是清掉最后一条助手消息，
  // 用同一条用户消息重新请求——而不是让用户再打一遍。
  // 复用原来的 client_msg_id，后端据此不会重复插入用户消息。
  async function retry(conversationId: number): Promise<void> {
    const conversation = useConversationStore()
    const bucket = conversation.messages[conversationId] ?? []

    let lastUserIndex = -1
    for (let i = bucket.length - 1; i >= 0; i -= 1) {
      if (bucket[i].role === 'user') {
        lastUserIndex = i
        break
      }
    }
    if (lastUserIndex === -1) return

    const userMessage = bucket[lastUserIndex]
    // 移除其后的助手消息（失败的占位或半截内容），避免界面上堆积
    for (const item of bucket.slice(lastUserIndex + 1)) {
      if (item.role === 'assistant') conversation.removeMessage(conversationId, item.id)
    }

    const clientMsgId = userMessage.client_msg_id ?? makeClientMsgId()
    await streamReply(conversationId, userMessage.content, clientMsgId)
  }

  function stop(): void {
    controller.value?.abort()
    controller.value = null
    streaming.value = false
  }

  function clearCrisis(): void {
    crisis.value = null
  }

  return {
    streaming,
    crisis,
    lastError,
    rateLimitedUntil,
    send,
    retry,
    stop,
    clearCrisis,
    clearRateLimit,
  }
})

