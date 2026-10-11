<script setup lang="ts">
// 危机事件复核（开发文档 §7.7 / §10.8）。数据走 api/admin.ts。

import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import CrisisEventTable from '@/components/CrisisEventTable.vue'
import * as adminApi from '@/api/admin'
import { ApiError } from '@/api/client'
import type { CrisisEvent } from '@/api/types'

const events = ref<CrisisEvent[]>([])
const loading = ref(false)
const errorHint = ref<string | null>(null)
const levelFilter = ref<'high' | 'medium' | ''>('')
const onlyUnreviewed = ref(false)

const visibleEvents = computed(() =>
  events.value.filter((item) => {
    if (levelFilter.value && item.level !== levelFilter.value) return false
    if (onlyUnreviewed.value && item.reviewed) return false
    return true
  }),
)

const unreviewedHigh = computed(
  () => events.value.filter((item) => item.level === 'high' && !item.reviewed).length,
)

function notify(err: unknown, fallback: string): void {
  const message = err instanceof ApiError ? err.message : fallback
  errorHint.value = message
  ElMessage.warning(message)
}

async function fetchEvents(): Promise<void> {
  loading.value = true
  try {
    const page = await adminApi.listCrisisEvents({ page: 1, size: 50 })
    events.value = page.items
    errorHint.value = null
  } catch (err) {
    events.value = []
    notify(err, '加载失败')
  } finally {
    loading.value = false
  }
}

async function review(event: CrisisEvent): Promise<void> {
  let note = ''
  try {
    const result = await ElMessageBox.prompt(
      '记录你做了什么（例如：已电话联系，已发送关怀邮件）。这条记录会写进审计日志。',
      '标记为已联系',
      { confirmButtonText: '保存', cancelButtonText: '取消', inputPlaceholder: '可选' },
    )
    note = result.value ?? ''
  } catch {
    return
  }

  try {
    await adminApi.reviewCrisisEvent(event.id, { follow_up_status: 'contacted', note })
    ElMessage.success('已记录')
    await fetchEvents()
  } catch (err) {
    notify(err, '操作失败')
  }
}

function detail(event: CrisisEvent): void {
  ElMessageBox.alert(
    `触发来源：${event.source}\n命中词：${event.matched_terms ?? '-'}\n片段：${event.snippet ?? '-'}`,
    '事件详情',
    { confirmButtonText: '知道了' },
  )
}

onMounted(fetchEvents)
</script>

<template>
  <div class="page">
    <el-alert
      v-if="errorHint"
      class="section"
      type="warning"
      :closable="false"
      show-icon
      :title="errorHint"
    />

    <el-alert
      v-if="unreviewedHigh > 0"
      class="section"
      type="error"
      :closable="false"
      show-icon
      :title="`有 ${unreviewedHigh} 条高危事件尚未复核`"
      description="按 SOP，高危且未复核的事件应当在工作时间内优先处理：先看脱敏片段与上下文，再决定联系或报警。"
    />

    <el-card shadow="never" class="section">
      <template #header>
        <div class="head">
          <span>危机事件</span>
          <div class="filters">
            <el-radio-group v-model="levelFilter" size="small">
              <el-radio-button label="">全部</el-radio-button>
              <el-radio-button label="high">高危</el-radio-button>
              <el-radio-button label="medium">中危</el-radio-button>
            </el-radio-group>
            <el-checkbox v-model="onlyUnreviewed" size="small">只看未复核</el-checkbox>
            <el-button size="small" @click="fetchEvents">刷新</el-button>
          </div>
        </div>
      </template>

      <CrisisEventTable
        :events="visibleEvents"
        :loading="loading"
        @review="review"
        @detail="detail"
      />
    </el-card>
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

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.filters {
  display: flex;
  gap: 10px;
  align-items: center;
}
</style>

