<script setup lang="ts">
/** 会话列表（开发文档 §11.3）。从 ChatView 里拆出来。 */

import type { Conversation } from '@/api/types'
import { plainPreview } from '@/utils/markdown'

defineProps<{
  conversations: Conversation[]
  activeId: number | null
  loading?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  select: [id: number]
  create: []
  rename: [conversation: Conversation]
  remove: [conversation: Conversation]
}>()

function formatDay(iso: string): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso.slice(0, 10)
  const today = new Date()
  const isToday = date.toDateString() === today.toDateString()
  return isToday
    ? `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
    : `${date.getMonth() + 1}/${date.getDate()}`
}
</script>

<template>
  <div class="conv-list">
    <el-button
      class="new-btn"
      type="primary"
      plain
      :disabled="disabled"
      @click="emit('create')"
    >
      ＋ 新的对话
    </el-button>

    <div class="scroll">
      <!-- 首次加载用骨架屏：比一个转圈的遮罩更能提示"这里将出现一个列表" -->
      <el-skeleton v-if="loading && !conversations.length" :rows="4" animated />

      <div
        v-for="item in loading && !conversations.length ? [] : conversations"
        :key="item.id"
        class="item"
        :class="{ active: item.id === activeId }"
        role="button"
        tabindex="0"
        :aria-label="`打开会话：${item.title}`"
        @click="emit('select', item.id)"
        @keydown.enter="emit('select', item.id)"
      >
        <div class="line">
          <span
            v-if="item.status === 'paused'"
            class="dot-paused"
            title="因安全原因暂停"
          />
          <span class="title">{{ plainPreview(item.title, 14) }}</span>
          <span class="day psy-hint">{{ formatDay(item.updated_at) }}</span>
        </div>
        <div class="ops">
          <el-button text size="small" @click.stop="emit('rename', item)">重命名</el-button>
          <el-button text size="small" type="danger" @click.stop="emit('remove', item)">
            删除
          </el-button>
        </div>
      </div>

      <el-empty v-if="!loading && !conversations.length" description="还没有对话" :image-size="60" />
    </div>
  </div>
</template>

<style scoped>
.conv-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px;
  background: var(--psy-panel);
  border-right: 1px solid var(--psy-border);
}

.new-btn {
  width: 100%;
  margin-bottom: 10px;
}

.scroll {
  flex: 1;
  overflow-y: auto;
}

.item {
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  outline: none;
}

.item:hover,
.item:focus-visible {
  background: #f0f2f5;
}

.item.active {
  background: #eef2f8;
}

.line {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 13px;
}

.title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.day {
  flex: 0 0 auto;
}

.dot-paused {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--psy-crisis-medium);
}

/* 操作按钮平时隐藏，hover 或聚焦时才出现，避免列表显得杂乱 */
.ops {
  display: none;
  gap: 2px;
  margin-top: 2px;
}

.item:hover .ops,
.item:focus-within .ops,
.item.active .ops {
  display: flex;
}
</style>

