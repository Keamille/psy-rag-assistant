<script setup lang="ts">
/**
 * 单条引用来源卡片（开发文档 §8.8）。
 *
 * 展示的是**原文片段**，不是模型转述——这样用户才能自己核对。
 * 卡片 id 形如 `source-3`，供 MarkdownRenderer 的 [3] 角标滚动定位。
 */

import { computed } from 'vue'

import type { SourceItem } from '@/api/types'

const props = defineProps<{ source: SourceItem; highlighted?: boolean }>()

const anchorId = computed(() => `source-${props.source.index}`)
</script>

<template>
  <div :id="anchorId" class="source-card" :class="{ highlighted }">
    <div class="head">
      <span class="index">[{{ source.index }}]</span>
      <span class="title">{{ source.document_title }}</span>
    </div>
    <div class="meta psy-hint">
      <span v-if="source.section_path">{{ source.section_path }}</span>
      <span v-if="source.page">· 第 {{ source.page }} 页</span>
      <span v-if="source.score !== null">· 相关度 {{ source.score.toFixed(2) }}</span>
    </div>
    <div class="snippet">{{ source.snippet }}</div>
  </div>
</template>

<style scoped>
.source-card {
  padding: 8px 10px;
  margin-bottom: 6px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: #f7f8fa;
  transition: border-color 0.3s ease, background 0.3s ease;
}

.source-card.highlighted {
  border-color: var(--psy-primary);
  background: #eef2f8;
}

.head {
  display: flex;
  gap: 6px;
  align-items: baseline;
  font-size: 13px;
  font-weight: 500;
}

.index {
  color: var(--psy-primary);
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.snippet {
  margin-top: 4px;
  font-size: 12px;
  color: var(--psy-text-soft);
  white-space: pre-wrap;
}
</style>

