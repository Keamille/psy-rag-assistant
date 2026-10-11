<script setup lang="ts">
/** 文档列表（开发文档 §11.3）。从 DocumentsView 里拆出来。 */

import type { KnowledgeDocument } from '@/api/types'

defineProps<{ documents: KnowledgeDocument[]; loading?: boolean }>()

const emit = defineEmits<{
  preview: [document: KnowledgeDocument]
  reindex: [document: KnowledgeDocument]
  remove: [document: KnowledgeDocument]
}>()

const STATUS_TAG: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
  ready: 'success',
  pending: 'info',
  processing: 'warning',
  failed: 'danger',
}

const STATUS_TEXT: Record<string, string> = {
  ready: '可用',
  pending: '排队中',
  processing: '处理中',
  failed: '失败',
}
</script>

<template>
  <el-skeleton v-if="loading && !documents.length" :rows="5" animated />

  <el-table
    v-else
    :data="documents"
    v-loading="loading"
    empty-text="暂无文档"
    size="small"
  >
    <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />

    <el-table-column label="类型" width="80">
      <template #default="{ row }">
        <el-tag size="small" effect="plain" type="info">{{ row.source_type }}</el-tag>
      </template>
    </el-table-column>

    <el-table-column label="状态" width="100">
      <template #default="{ row }">
        <el-tooltip
          :disabled="!row.error_message"
          :content="row.error_message || ''"
          placement="top"
        >
          <el-tag :type="STATUS_TAG[row.status] ?? 'info'" size="small" effect="plain">
            {{ STATUS_TEXT[row.status] ?? row.status }}
          </el-tag>
        </el-tooltip>
      </template>
    </el-table-column>

    <el-table-column prop="chunk_count" label="分块" width="70" align="right" />
    <el-table-column prop="version" label="版本" width="70" align="right" />

    <el-table-column label="来源" width="80">
      <template #default="{ row }">
        <span class="psy-hint">{{ row.is_builtin ? '内置' : '上传' }}</span>
      </template>
    </el-table-column>

    <el-table-column prop="created_at" label="时间" width="150">
      <template #default="{ row }">
        <span class="psy-hint">{{ String(row.created_at).replace('T', ' ').slice(0, 16) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="操作" width="190" fixed="right">
      <template #default="{ row }">
        <el-button text size="small" @click="emit('preview', row)">分块</el-button>
        <el-button text size="small" @click="emit('reindex', row)">重建索引</el-button>
        <el-button text size="small" type="danger" @click="emit('remove', row)">删除</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

