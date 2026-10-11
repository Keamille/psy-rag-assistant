<script setup lang="ts">
/**
 * 单条消息气泡（开发文档 §11.3）。
 *
 * 本组件只负责"怎么排"，渲染细节交给子组件：
 * MarkdownRenderer 负责转义与净化，SourcePanel / SourceCard 负责引用溯源。
 */

import { computed, ref } from 'vue'

import CrisisCard from '@/components/CrisisCard.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import SourcePanel from '@/components/SourcePanel.vue'
import TypingIndicator from '@/components/TypingIndicator.vue'
import type { ChatMessage } from '@/api/types'

const props = defineProps<{ message: ChatMessage }>()
const emit = defineEmits<{ resume: []; retry: [] }>()

const isUser = computed(() => props.message.role === 'user')
const isCard = computed(() => props.message.role === 'system_card')
const sourceCount = computed(() => props.message.sources?.length ?? 0)

/** 生成中但一个字都还没到 —— 此时显示等待动画而不是空气泡 */
const waitingFirstToken = computed(
  () => props.message.streaming === true && !props.message.content,
)

const sourcePanel = ref<InstanceType<typeof SourcePanel> | null>(null)

function onCite(index: number): void {
  sourcePanel.value?.focusSource(index)
}

const timeText = computed(() => {
  const raw = props.message.created_at
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return ''
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
})

// 只有助手消息失败时才给"重新生成"——用户消息失败重发没有意义
const canRetry = computed(
  () => !isUser.value && Boolean(props.message.error) && !props.message.streaming,
)
</script>

<template>
  <div class="row" :class="isUser ? 'from-user' : 'from-assistant'">
    <div class="bubble" :class="{ 'card-bubble': isCard, 'is-user': isUser }">
      <TypingIndicator v-if="waitingFirstToken" />

      <template v-else>
        <MarkdownRenderer
          v-if="!isCard"
          :content="message.content"
          :source-count="sourceCount"
          @cite="onCite"
        />
        <div v-else class="plain">{{ message.content }}</div>
        <span v-if="message.streaming" class="cursor" aria-hidden="true">▍</span>
      </template>

      <div v-if="timeText" class="time psy-hint">{{ timeText }}</div>

      <el-alert
        v-if="message.error"
        class="msg-error"
        type="warning"
        :closable="false"
        show-icon
        :title="message.error.message"
      />

      <!--
        重新生成按钮（开发文档 §11.8）。
        刻意不自动重试：断流时自动重试会产生重复消息与重复计费，
        而且用户看不到发生了什么。给一个按钮，让重试成为明确的选择。
      -->
      <div v-if="canRetry" class="retry-row">
        <el-button size="small" type="primary" plain @click="emit('retry')">
          重新生成
        </el-button>
        <span class="psy-hint">也可以直接在下方补充说明后重新发送</span>
      </div>

      <CrisisCard v-if="message.crisis" :payload="message.crisis" @resume="emit('resume')" />

      <SourcePanel
        v-if="!isUser && message.sources?.length"
        ref="sourcePanel"
        :sources="message.sources"
      />
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  margin-bottom: 16px;
}

.from-user {
  justify-content: flex-end;
}

.from-assistant {
  justify-content: flex-start;
}

.bubble {
  position: relative;
  max-width: min(760px, 82%);
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--psy-panel);
  border: 1px solid var(--psy-border);
  box-shadow: 0 1px 2px rgb(0 0 0 / 3%);
}

.bubble.is-user {
  background: #eef2f8;
  border-color: #dde5f0;
  border-bottom-right-radius: 4px;
}

.from-assistant .bubble {
  border-bottom-left-radius: 4px;
}

.card-bubble {
  background: #fbfcfe;
  border-left: 3px solid var(--psy-primary);
}

.plain {
  white-space: pre-wrap;
  word-break: break-word;
}

.cursor {
  color: var(--psy-primary);
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.time {
  margin-top: 6px;
  text-align: right;
  font-size: 11px;
}

.msg-error {
  margin-top: 8px;
}

.retry-row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 8px;
}
</style>

