<script setup lang="ts">
// 对话主页（开发文档 §11.2）。
//
// 布局：左侧会话列表 + 右侧消息流 + 底部输入区；移动端把列表收进抽屉。

import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import ChatInput from '@/components/ChatInput.vue'
import ConversationList from '@/components/ConversationList.vue'
import DisclaimerCard from '@/components/DisclaimerCard.vue'
import MessageBubble from '@/components/MessageBubble.vue'
import { ApiError } from '@/api/client'
import { systemApi } from '@/api/system'
import type { Conversation, MetaConfig } from '@/api/types'
import { useChatStore } from '@/stores/chat'
import { useConversationStore } from '@/stores/conversation'

const conversation = useConversationStore()
const chat = useChatStore()
const route = useRoute()
const router = useRouter()

const metaConfig = ref<MetaConfig | null>(null)
const bodyRef = ref<HTMLElement | null>(null)
const drawerVisible = ref(false)

// 首次进入时的引导问题（开发文档 §11.8）。点击即新建会话并把这句话发出去，
// 降低"面对空白输入框不知道说什么"的门槛——这在心理支持场景里尤其重要。
const SAMPLE_QUESTIONS = [
  '最近总是睡不着，压力有点大',
  '一想到明天要上班就心慌',
  '怎么跟家人说我想找心理咨询',
]

const messages = computed(() => conversation.activeMessages)
const activeId = computed(() => conversation.activeId)
const inputDisabled = computed(() => activeId.value === null || conversation.isPaused)

// 限流解禁倒计时：后端在 429 里给了 retry_after，这里换算成剩余秒数
const disabledSeconds = computed(() => {
  const until = chat.rateLimitedUntil
  if (!until) return 0
  return Math.max(0, Math.ceil((until - Date.now()) / 1000))
})

async function loadMeta(): Promise<void> {
  try {
    metaConfig.value = await systemApi.metaConfig()
  } catch {
    // 拿不到配置时界面会退化成一段固定文案，不影响使用
    metaConfig.value = null
  }
}

function scrollToBottom(): void {
  nextTick(() => {
    const el = bodyRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function selectConversation(id: number): void {
  conversation.select(id)
  drawerVisible.value = false
  router.replace({ name: 'chat-detail', params: { id: String(id) } })
  void conversation.fetchMessages(id)
  scrollToBottom()
}

async function createConversation(): Promise<Conversation | null> {
  const created = await conversation.create()
  if (created) {
    router.replace({ name: 'chat-detail', params: { id: String(created.id) } })
    drawerVisible.value = false
  } else if (conversation.lastError) {
    ElMessage.error(conversation.lastError)
  }
  return created
}

/** 点击示例问题：没有会话就先建一个，然后直接把问题发出去 */
async function askSample(question: string): Promise<void> {
  let target = conversation.activeConversation
  if (!target) {
    target = await createConversation()
  }
  if (!target) return
  await handleSend(question)
}

async function renameConversation(item: Conversation): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('新的标题', '重命名会话', {
      inputValue: item.title,
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    await conversation.rename(item, value)
  } catch {
    /* 用户取消 */
  }
}

async function removeConversation(item: Conversation): Promise<void> {
  try {
    await ElMessageBox.confirm(`删除「${item.title}」及其全部消息？`, '删除会话', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await conversation.remove(item)
  if (conversation.activeId === null) {
    router.replace({ name: 'chat' })
  }
}

async function handleSend(text: string): Promise<void> {
  if (activeId.value === null) return
  scrollToBottom()
  await chat.send(activeId.value, text)
  scrollToBottom()
  reportChatError()
}

async function handleRetry(): Promise<void> {
  if (activeId.value === null) return
  await chat.retry(activeId.value)
  scrollToBottom()
  reportChatError()
}

function reportChatError(): void {
  if (chat.lastError?.code === 1005) {
    // 倒计时由 ChatInput 显示，这里不再重复弹提示
  } else if (chat.lastError) {
    ElMessage.warning(chat.lastError.message)
  }
}

async function handleResume(): Promise<void> {
  const target = conversation.activeConversation
  if (!target) return
  const ok = await conversation.resume(target)
  if (ok) {
    ElMessage.success('会话已解锁，该操作已记入审计日志')
  } else if (conversation.lastError) {
    ElMessage.error(conversation.lastError)
  }
}

onMounted(async () => {
  await loadMeta()
  await conversation.fetchList()

  const routeId = Number(route.params.id)
  if (routeId && conversation.list.some((item) => item.id === routeId)) {
    conversation.select(routeId)
    await conversation.fetchMessages(routeId)
  }
  scrollToBottom()
})

watch(
  () => route.params.id,
  (value) => {
    const id = Number(value)
    if (id && id !== conversation.activeId && conversation.list.some((item) => item.id === id)) {
      conversation.select(id)
      void conversation.fetchMessages(id)
      scrollToBottom()
    }
  },
)

watch(
  () => messages.value.length,
  () => scrollToBottom(),
)
</script>

<template>
  <div class="chat-page">
    <aside class="sidebar-desktop">
      <ConversationList
        :conversations="conversation.list"
        :active-id="activeId"
        :loading="conversation.loading"
        @select="selectConversation"
        @create="createConversation"
        @rename="renameConversation"
        @remove="removeConversation"
      />
    </aside>

    <el-drawer v-model="drawerVisible" direction="ltr" size="280px" :with-header="false">
      <ConversationList
        :conversations="conversation.list"
        :active-id="activeId"
        :loading="conversation.loading"
        @select="selectConversation"
        @create="createConversation"
        @rename="renameConversation"
        @remove="removeConversation"
      />
    </el-drawer>

    <section class="chat-main">
      <header class="chat-head">
        <el-button class="menu-btn" text aria-label="打开会话列表" @click="drawerVisible = true">
          ☰
        </el-button>
        <div class="chat-title">
          {{ conversation.activeConversation?.title ?? '新的对话' }}
        </div>
        <el-tag v-if="conversation.isPaused" type="danger" effect="plain" size="small">
          已因安全原因暂停
        </el-tag>
      </header>

      <div ref="bodyRef" class="chat-body" role="log" aria-live="polite" aria-label="对话内容">
        <DisclaimerCard :config="metaConfig" />

        <template v-if="messages.length">
          <MessageBubble
            v-for="message in messages"
            :key="message.id"
            :message="message"
            @resume="handleResume"
            @retry="handleRetry"
          />
        </template>

        <!-- 首次进入的引导（开发文档 §11.8） -->
        <div v-else class="welcome">
          <div class="welcome-title">你可以从这里开始</div>
          <div class="psy-hint welcome-sub">
            这些都是常见困扰，点一下就把问题发出去；也可以直接在下方输入。
          </div>
          <div class="samples">
            <button
              v-for="question in SAMPLE_QUESTIONS"
              :key="question"
              class="sample-card"
              type="button"
              @click="askSample(question)"
            >
              {{ question }}
            </button>
          </div>
        </div>
      </div>

      <ChatInput
        :disabled="inputDisabled"
        :streaming="chat.streaming"
        :max-length="metaConfig?.max_message_length ?? 4000"
        :disabled-seconds="disabledSeconds"
        @send="handleSend"
        @stop="chat.stop"
      />
    </section>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex: 1;
  min-height: 0;
}

.sidebar-desktop {
  width: 250px;
  flex: 0 0 250px;
}

.chat-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.chat-head {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 16px;
  background: var(--psy-panel);
  border-bottom: 1px solid var(--psy-border);
}

.chat-title {
  flex: 1;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-btn {
  display: none;
  font-size: 18px;
}

.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  scroll-behavior: smooth;
}

.welcome {
  margin-top: 32px;
  text-align: center;
}

.welcome-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 6px;
}

.welcome-sub {
  margin-bottom: 18px;
}

.samples {
  display: grid;
  gap: 10px;
  max-width: 520px;
  margin: 0 auto;
}

.sample-card {
  padding: 14px 16px;
  border: 1px solid var(--psy-border);
  border-radius: var(--psy-radius);
  background: var(--psy-panel);
  color: var(--psy-text);
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.sample-card:hover,
.sample-card:focus-visible {
  border-color: var(--psy-primary);
  box-shadow: var(--psy-shadow);
  outline: none;
}

@media (max-width: 767px) {
  .sidebar-desktop {
    display: none;
  }

  .menu-btn {
    display: inline-flex;
  }
}
</style>

