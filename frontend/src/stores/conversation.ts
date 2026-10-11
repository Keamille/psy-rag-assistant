// 会话列表与消息。
//
// 加载失败时只记 lastError，由页面决定怎么展示——store 不弹提示。

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as conversationApi from '@/api/conversations'
import { ApiError } from '@/api/client'
import type { ChatMessage, Conversation } from '@/api/types'

export const useConversationStore = defineStore('conversation', () => {
  const list = ref<Conversation[]>([])
  const activeId = ref<number | null>(null)
  const messages = ref<Record<number, ChatMessage[]>>({})
  const loading = ref(false)
  const lastError = ref<string | null>(null)

  const activeConversation = computed(
    () => list.value.find((item) => item.id === activeId.value) ?? null,
  )
  const activeMessages = computed(() =>
    activeId.value === null ? [] : messages.value[activeId.value] ?? [],
  )
  const isPaused = computed(() => activeConversation.value?.status === 'paused')

  function handleError(err: unknown, fallback: string): void {
    lastError.value = err instanceof ApiError ? err.message : fallback
  }

  async function fetchList(): Promise<void> {
    loading.value = true
    lastError.value = null
    try {
      const page = await conversationApi.listConversations({ page: 1, size: 50 })
      list.value = page.items
    } catch (err) {
      list.value = []
      handleError(err, '加载会话失败')
    } finally {
      loading.value = false
    }
  }

  async function fetchMessages(conversationId: number): Promise<void> {
    try {
      const page = await conversationApi.listMessages(conversationId, { page: 1, size: 50 })
      // 后端按时间倒序返回，界面上要正序显示
      messages.value[conversationId] = [...page.items].reverse()
    } catch (err) {
      handleError(err, '加载消息失败')
    }
  }

  async function create(title?: string): Promise<Conversation | null> {
    try {
      const created = await conversationApi.createConversation(title)
      list.value = [created, ...list.value]
      messages.value[created.id] = []
      activeId.value = created.id
      return created
    } catch (err) {
      handleError(err, '创建会话失败')
      return null
    }
  }

  async function rename(conversation: Conversation, title: string): Promise<void> {
    if (!title.trim()) return
    try {
      const updated = await conversationApi.updateConversation(conversation.id, { title })
      Object.assign(conversation, updated)
    } catch (err) {
      handleError(err, '重命名失败')
    }
  }

  async function remove(conversation: Conversation): Promise<void> {
    try {
      await conversationApi.deleteConversation(conversation.id)
      list.value = list.value.filter((item) => item.id !== conversation.id)
      delete messages.value[conversation.id]
      if (activeId.value === conversation.id) {
        activeId.value = list.value[0]?.id ?? null
      }
    } catch (err) {
      handleError(err, '删除失败')
    }
  }

  // 危机中断后恢复会话。成功后会话从 paused 回到 active。
  async function resume(conversation: Conversation): Promise<boolean> {
    try {
      const updated = await conversationApi.resumeConversation(conversation.id)
      Object.assign(conversation, updated)
      return true
    } catch (err) {
      handleError(err, '解锁失败')
      return false
    }
  }

  function appendMessage(conversationId: number, message: ChatMessage): ChatMessage {
    const bucket = messages.value[conversationId] ?? []
    bucket.push(message)
    messages.value[conversationId] = bucket
    return message
  }

  function updateMessage(
    conversationId: number,
    messageId: ChatMessage['id'],
    patch: Partial<ChatMessage>,
  ): void {
    const bucket = messages.value[conversationId]
    if (!bucket) return
    const index = bucket.findIndex((item) => item.id === messageId)
    if (index === -1) return
    bucket[index] = { ...bucket[index], ...patch }
  }

  function removeMessage(conversationId: number, messageId: ChatMessage['id']): void {
    const bucket = messages.value[conversationId]
    if (!bucket) return
    messages.value[conversationId] = bucket.filter((item) => item.id !== messageId)
  }

  function select(conversationId: number | null): void {
    activeId.value = conversationId
  }

  return {
    list,
    activeId,
    messages,
    loading,
    lastError,
    activeConversation,
    activeMessages,
    isPaused,
    fetchList,
    fetchMessages,
    create,
    rename,
    remove,
    resume,
    appendMessage,
    updateMessage,
    removeMessage,
    select,
  }
})

