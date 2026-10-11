<script setup lang="ts">
// 输入区（开发文档 §11.2 / §11.8 / §11.9）。
//
// 这里承担三件事：
//   1. 限流倒计时：从 429 的 retry_after 起倒数，归零自动恢复输入
//   2. 草稿保留：内容实时写入 sessionStorage，令牌过期跳登录再回来时还在
//   3. 键盘：Enter 发送、Shift+Enter 换行、Esc 停止生成

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = withDefaults(
  defineProps<{
    disabled?: boolean
    streaming?: boolean
    maxLength?: number
    /** 距离限流解禁还有多少秒；大于 0 时输入被锁定 */
    disabledSeconds?: number
  }>(),
  { disabled: false, streaming: false, maxLength: 4000, disabledSeconds: 0 },
)

const emit = defineEmits<{ send: [text: string]; stop: [] }>()

const DRAFT_KEY = 'psy_chat_draft'

const text = ref(sessionStorage.getItem(DRAFT_KEY) ?? '')
const remaining = ref(0)
let timer: number | undefined

const maxLength = computed(() => props.maxLength)
const rateLimited = computed(() => remaining.value > 0)
const locked = computed(() => props.disabled || rateLimited.value)
const canSend = computed(() => !locked.value && !props.streaming && text.value.trim().length > 0)

// 草稿实时落盘：用户可能在写完之前就被 401 弹回登录页
watch(text, (value) => {
  if (value) sessionStorage.setItem(DRAFT_KEY, value)
  else sessionStorage.removeItem(DRAFT_KEY)
})

// 倒计时。props 变化时重启动，归零后自动解锁。
watch(
  () => props.disabledSeconds,
  (seconds) => {
    window.clearInterval(timer)
    remaining.value = Math.max(0, Math.floor(seconds ?? 0))
    if (remaining.value <= 0) return
    timer = window.setInterval(() => {
      remaining.value -= 1
      if (remaining.value <= 0) window.clearInterval(timer)
    }, 1000)
  },
  { immediate: true },
)

onBeforeUnmount(() => window.clearInterval(timer))

function submit(): void {
  if (!canSend.value) return
  if (text.value.length > maxLength.value) {
    ElMessage.warning(`单条消息不能超过 ${maxLength.value} 字`)
    return
  }
  emit('send', text.value.trim())
  text.value = ''
  sessionStorage.removeItem(DRAFT_KEY)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
    return
  }
  // Esc 停止生成：生成中才有意义，否则不拦截
  if (event.key === 'Escape' && props.streaming) {
    event.preventDefault()
    emit('stop')
  }
}
</script>

<template>
  <div class="composer">
    <el-alert
      v-if="rateLimited"
      class="rate-limit"
      type="warning"
      :closable="false"
      show-icon
      :title="`操作过于频繁，请等待 ${remaining} 秒后再发送`"
    />

    <el-input
      v-model="text"
      type="textarea"
      :rows="3"
      resize="none"
      :disabled="locked"
      :maxlength="maxLength"
      placeholder="说说你现在的情况……（Enter 发送，Shift+Enter 换行，Esc 停止生成）"
      aria-label="消息输入框"
      @keydown="onKeydown"
    />

    <div class="composer-footer">
      <span class="psy-hint">{{ text.length }} / {{ maxLength }}</span>
      <div class="composer-actions">
        <el-button v-if="streaming" @click="emit('stop')">停止生成（Esc）</el-button>
        <el-button type="primary" :disabled="!canSend" @click="submit">发送</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.composer {
  padding: 12px 16px 16px;
  border-top: 1px solid var(--psy-border);
  background: var(--psy-panel);
}

.rate-limit {
  margin-bottom: 8px;
}

.composer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.composer-actions {
  display: flex;
  gap: 8px;
}
</style>

