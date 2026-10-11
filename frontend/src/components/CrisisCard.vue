<script setup lang="ts">
/** 危机资源卡片（开发文档 11.7）。
 *  文案来自后端 risk 事件，前端不硬编码，避免与后端口径漂移。 */

import { computed } from 'vue'

import type { CrisisCardPayload } from '@/api/types'

const props = defineProps<{ payload: CrisisCardPayload }>()
const emit = defineEmits<{ resume: []; openHotline: [phone: string] }>()

const isHigh = computed(() => props.payload.level === 'high')
const card = computed(() => props.payload.card)
</script>

<template>
  <el-card
    class="crisis-card"
    :class="isHigh ? 'level-high' : 'level-medium'"
    shadow="never"
    role="alert"
  >
    <div class="crisis-title">{{ card?.title ?? '我很在意你刚才说的话' }}</div>
    <p class="crisis-body">{{ card?.body }}</p>

    <div class="hotline-list">
      <div v-for="item in payload.hotlines" :key="item.phone" class="hotline-item">
        <div class="hotline-head">
          <span class="hotline-name">{{ item.name }}</span>
          <el-button
            type="primary"
            link
            tag="a"
            :href="`tel:${item.phone.replace(/\s/g, '')}`"
            @click="emit('openHotline', item.phone)"
          >
            {{ item.phone }}
          </el-button>
        </div>
        <div class="psy-hint">{{ item.description }}</div>
      </div>
    </div>

    <el-alert
      class="emergency"
      type="error"
      :closable="false"
      show-icon
      title="如你或他人正处于紧急危险中，请立即拨打 120 或 110"
    />

    <div v-if="isHigh" class="crisis-actions">
      <el-button type="primary" plain @click="emit('resume')">
        {{ card?.confirm_text ?? '我目前是安全的，继续对话' }}
      </el-button>
      <span class="psy-hint">确认后本会话才会解锁，该操作会被记录在审计日志中。</span>
    </div>
  </el-card>
</template>

<style scoped>
.crisis-card {
  margin: 12px 0;
}

.level-high {
  border: 1px solid var(--psy-crisis-high);
  background: #fdf3f2;
}

.level-medium {
  border: 1px solid var(--psy-crisis-medium);
  background: #fdf7ee;
}

.crisis-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 6px;
}

.crisis-body {
  margin: 0 0 12px;
}

.hotline-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.hotline-head {
  display: flex;
  gap: 10px;
  align-items: baseline;
}

.hotline-name {
  font-weight: 500;
}

.emergency {
  margin-bottom: 12px;
}

.crisis-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}
</style>

