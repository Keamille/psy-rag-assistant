<script setup lang="ts">
import { computed } from 'vue'

import type { MetaConfig } from '@/api/types'

const props = defineProps<{ config: MetaConfig | null }>()

const html = computed(() => {
  // 免责声明来自后端，用极简转换避免额外依赖；正式内容以 Markdown 呈现
  if (!props.config) return ''
  return props.config.disclaimer_markdown
    .split('\n')
    .filter((line) => line.trim())
    .map((line) => {
      if (line.startsWith('## ')) return `<div class="disclaimer-title">${line.slice(3)}</div>`
      if (line.startsWith('- ')) return `<li>${line.slice(2)}</li>`
      return `<p>${line}</p>`
    })
    .join('')
})
</script>

<template>
  <el-card shadow="never" class="disclaimer">
    <div v-if="config" class="psy-markdown" v-html="html" />
    <div v-else class="psy-hint">
      未能加载免责声明（/meta/config 不可达）。本助手不能替代专业诊断与治疗。
    </div>
  </el-card>
</template>

<style scoped>
.disclaimer {
  border-left: 3px solid var(--psy-primary);
  background: #fbfcfe;
}

:deep(.disclaimer-title) {
  font-weight: 600;
  margin-bottom: 6px;
}

:deep(li) {
  margin-left: 18px;
}
</style>

