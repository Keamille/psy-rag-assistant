<script setup lang="ts">
/** 危机事件表（开发文档 §11.3 / §10.8）。从 CrisisView 里拆出来。 */

import type { CrisisEvent } from '@/api/types'

defineProps<{ events: CrisisEvent[]; loading?: boolean }>()

const emit = defineEmits<{
  review: [event: CrisisEvent]
  detail: [event: CrisisEvent]
}>()

const ACTION_TEXT: Record<string, string> = {
  interrupted: '已中断应答',
  warned_and_continued: '风险关切后继续',
}

const FOLLOW_UP_TEXT: Record<string, string> = {
  pending: '待跟进',
  contacted: '已联系',
  closed: '已关闭',
}
</script>

<template>
  <el-skeleton v-if="loading && !events.length" :rows="5" animated />

  <el-table
    v-else
    :data="events"
    v-loading="loading"
    empty-text="暂无危机事件"
    size="small"
  >
    <el-table-column label="等级" width="80">
      <template #default="{ row }">
        <el-tag
          :type="row.level === 'high' ? 'danger' : 'warning'"
          size="small"
          effect="dark"
        >
          {{ row.level === 'high' ? '高危' : '中危' }}
        </el-tag>
      </template>
    </el-table-column>

    <el-table-column label="时间" width="150">
      <template #default="{ row }">
        <span class="psy-hint">{{ String(row.created_at).replace('T', ' ').slice(0, 16) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="判定来源" width="90">
      <template #default="{ row }">
        <span class="psy-hint">{{ row.source }}</span>
      </template>
    </el-table-column>

    <el-table-column prop="matched_terms" label="命中词" width="140" show-overflow-tooltip />

    <el-table-column label="片段（已脱敏）" min-width="240">
      <template #default="{ row }">
        <span class="snippet">{{ row.snippet }}</span>
      </template>
    </el-table-column>

    <el-table-column label="处置" width="130">
      <template #default="{ row }">
        <span class="psy-hint">{{ ACTION_TEXT[row.action_taken] ?? row.action_taken }}</span>
      </template>
    </el-table-column>

    <el-table-column label="复核" width="150" fixed="right">
      <template #default="{ row }">
        <el-tag v-if="row.reviewed" type="success" size="small" effect="plain">
          {{ FOLLOW_UP_TEXT[row.follow_up_status ?? ''] ?? '已复核' }}
        </el-tag>
        <template v-else>
          <el-button text size="small" @click="emit('detail', row)">详情</el-button>
          <el-button text size="small" type="primary" @click="emit('review', row)">
            标记已联系
          </el-button>
        </template>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.snippet {
  font-size: 12px;
  color: var(--psy-text-soft);
}
</style>

