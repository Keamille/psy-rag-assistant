<script setup lang="ts">
/** 引用来源列表（开发文档 §8.8）：展示的是原文片段，不是模型转述。
 *  单条卡片的渲染抽到 SourceCard，这里只负责列表与折叠。 */

import { ref } from 'vue'

import SourceCard from '@/components/SourceCard.vue'
import type { SourceItem } from '@/api/types'

const props = defineProps<{ sources: SourceItem[] }>()

const expanded = ref(true)
const highlighted = ref<number | null>(null)

/** 供父组件在点击 [n] 角标时调用：滚动到对应卡片并短暂高亮 */
function focusSource(index: number): void {
  expanded.value = true
  highlighted.value = index
  requestAnimationFrame(() => {
    document.getElementById(`source-${index}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    })
  })
  window.setTimeout(() => {
    highlighted.value = null
  }, 1200)
}

defineExpose({ focusSource })
</script>

<template>
  <div v-if="props.sources.length" class="source-panel">
    <div class="source-head" role="button" tabindex="0" @click="expanded = !expanded">
      <span>依据的资料（{{ props.sources.length }}）</span>
      <span class="psy-hint">{{ expanded ? '收起' : '展开' }}</span>
    </div>
    <div v-show="expanded">
      <SourceCard
        v-for="source in props.sources"
        :key="source.index"
        :source="source"
        :highlighted="highlighted === source.index"
      />
    </div>
  </div>
</template>

<style scoped>
.source-panel {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--psy-border);
}

.source-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--psy-text-soft);
  margin-bottom: 6px;
  cursor: pointer;
}
</style>

