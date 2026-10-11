<script setup lang="ts">
// 概览统计（开发文档 §7.7）。

import { computed, onMounted, ref } from 'vue'

import * as adminApi from '@/api/admin'
import { ApiError } from '@/api/client'

const range = ref('7d')
const stats = ref<Record<string, number> | null>(null)
const loading = ref(false)
const hint = ref<string | null>(null)

const METRICS = [
  { key: 'new_users', label: '新增用户', suffix: '人' },
  { key: 'active_conversations', label: '活跃会话', suffix: '个' },
  { key: 'messages_total', label: '消息总数', suffix: '条' },
  { key: 'crisis_high', label: '高危事件', suffix: '条' },
  { key: 'avg_ttft_ms', label: '平均首字延迟', suffix: 'ms' },
  { key: 'avg_retrieval_ms', label: '平均检索耗时', suffix: 'ms' },
]

const cards = computed(() =>
  METRICS.map((item) => ({
    ...item,
    value: stats.value?.[item.key],
  })),
)

async function load(): Promise<void> {
  loading.value = true
  try {
    stats.value = await adminApi.getStatsOverview(range.value)
    hint.value = null
  } catch (err) {
    stats.value = null
    hint.value = err instanceof ApiError ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page" v-loading="loading">
    <el-alert
      v-if="hint"
      class="section"
      type="info"
      :closable="false"
      show-icon
      :title="hint"
    />

    <div class="toolbar">
      <el-radio-group v-model="range" size="small" @change="load">
        <el-radio-button label="24h">24 小时</el-radio-button>
        <el-radio-button label="7d">7 天</el-radio-button>
        <el-radio-button label="30d">30 天</el-radio-button>
      </el-radio-group>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-row :gutter="12">
      <el-col v-for="item in cards" :key="item.key" :xs="12" :sm="8" :md="4">
        <el-card shadow="never" class="metric">
          <div class="label psy-hint">{{ item.label }}</div>
          <div class="value">
            <span v-if="item.value !== undefined">{{ item.value }}</span>
            <span v-else class="psy-hint">—</span>
            <span class="unit psy-hint">{{ item.suffix }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page {
  padding: 16px;
  overflow-y: auto;
}

.section {
  margin-bottom: 16px;
}

.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}

.metric {
  margin-bottom: 12px;
}

.label {
  margin-bottom: 6px;
}

.value {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
}

.unit {
  margin-left: 4px;
  font-size: 12px;
  font-weight: 400;
}
</style>

