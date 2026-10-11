<script setup lang="ts">
/**
 * Markdown 渲染器（开发文档 §11.6）。
 *
 * 从 MessageBubble 里拆出来，因为 AI 输出、来源片段、后台文案都会用到它。
 *
 * **安全红线**：AI 输出属于不可信内容，必须经 DOMPurify 净化后才能 v-html。
 * 净化逻辑收在 utils/markdown.ts，不要在组件里绕过它。
 */

import { computed } from 'vue'

import { renderMarkdown } from '@/utils/markdown'

const props = withDefaults(
  defineProps<{
    content: string
    /** 已有的来源条数，用于判断 [n] 角标是否可点 */
    sourceCount?: number
  }>(),
  { sourceCount: 0 },
)

const emit = defineEmits<{ cite: [index: number] }>()

const html = computed(() => renderMarkdown(props.content, props.sourceCount))

function onClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null
  const index = target?.dataset?.cite
  if (index) emit('cite', Number(index))
}
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- 内容已经过 DOMPurify 净化 -->
  <div class="psy-markdown" @click="onClick" v-html="html" />
</template>

<style scoped>
.psy-markdown {
  word-break: break-word;
}
</style>

