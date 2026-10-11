<script setup lang="ts">
/**
 * 分块预览抽屉（开发文档 §11.3）。
 *
 * 用途：管理员上传后核对"切出来的块是否合理"——块太长会稀释检索精度，
 * 太短会丢上下文。这是调 CHUNK_SIZE / CHUNK_OVERLAP 时唯一能直接观察的地方。
 */

import type { KnowledgeChunk, KnowledgeDocument } from '@/api/types'

defineProps<{
  modelValue: boolean
  document: KnowledgeDocument | null
  chunks: KnowledgeChunk[]
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  reindex: [document: KnowledgeDocument]
}>()
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    :title="document ? `分块预览：${document.title}` : '分块预览'"
    size="640px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-if="document" class="head">
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item label="状态">{{ document.status }}</el-descriptions-item>
        <el-descriptions-item label="分块数">{{ document.chunk_count }}</el-descriptions-item>
        <el-descriptions-item label="版本">v{{ document.version }}</el-descriptions-item>
      </el-descriptions>
      <el-button class="reindex" size="small" @click="emit('reindex', document)">
        重建索引
      </el-button>
    </div>

    <div v-loading="loading" class="list">
      <el-card
        v-for="chunk in chunks"
        :key="chunk.id"
        shadow="never"
        class="chunk"
      >
        <div class="chunk-head">
          <span class="seq">#{{ chunk.seq + 1 }}</span>
          <span class="psy-hint">{{ chunk.section_path || '无章节信息' }}</span>
          <span v-if="chunk.page" class="psy-hint">· 第 {{ chunk.page }} 页</span>
          <span class="psy-hint">· {{ chunk.content.length }} 字符</span>
        </div>
        <div class="content">{{ chunk.content }}</div>
        <div class="psy-hint chroma">{{ chunk.chroma_id }}</div>
      </el-card>

      <el-empty v-if="!loading && !chunks.length" description="暂无分块" :image-size="60" />
    </div>
  </el-drawer>
</template>

<style scoped>
.head {
  margin-bottom: 12px;
}

.reindex {
  margin-top: 10px;
}

.list {
  max-height: calc(100vh - 260px);
  overflow-y: auto;
}

.chunk {
  margin-bottom: 8px;
  background: #fbfcfe;
}

.chunk-head {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  margin-bottom: 6px;
  font-size: 12px;
}

.seq {
  font-weight: 600;
  color: var(--psy-primary);
}

.content {
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.chroma {
  margin-top: 6px;
  font-family: Consolas, Monaco, monospace;
  font-size: 11px;
}
</style>

