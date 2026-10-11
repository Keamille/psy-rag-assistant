<script setup lang="ts">
// 知识库管理（开发文档 §7.7）。数据走 api/admin.ts。

import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'

import ChunkPreviewDrawer from '@/components/ChunkPreviewDrawer.vue'
import DocumentTable from '@/components/DocumentTable.vue'
import UploadDropzone from '@/components/UploadDropzone.vue'
import * as adminApi from '@/api/admin'
import { ApiError } from '@/api/client'
import type { KnowledgeChunk, KnowledgeDocument } from '@/api/types'

const documents = ref<KnowledgeDocument[]>([])
const chunks = ref<KnowledgeChunk[]>([])
const loading = ref(false)
const chunksLoading = ref(false)
const drawerVisible = ref(false)
const currentDocument = ref<KnowledgeDocument | null>(null)
const errorHint = ref<string | null>(null)

function notify(err: unknown, fallback: string): void {
  const message = err instanceof ApiError ? err.message : fallback
  errorHint.value = message
  ElMessage.warning(message)
}

async function fetchDocuments(): Promise<void> {
  loading.value = true
  try {
    const page = await adminApi.listDocuments({ page: 1, size: 50 })
    documents.value = page.items
    errorHint.value = null
  } catch (err) {
    documents.value = []
    notify(err, '加载文档失败')
  } finally {
    loading.value = false
  }
}

async function upload(options: UploadRequestOptions): Promise<void> {
  const form = new FormData()
  form.append('file', options.file)
  form.append('sensitivity', 'internal')
  try {
    await adminApi.uploadDocument(form)
    ElMessage.success('已进入入库队列')
    await fetchDocuments()
  } catch (err) {
    notify(err, '上传失败')
  }
}

async function preview(document: KnowledgeDocument): Promise<void> {
  currentDocument.value = document
  drawerVisible.value = true
  chunksLoading.value = true
  try {
    const page = await adminApi.listChunks(document.id, { page: 1, size: 50 })
    chunks.value = page.items
  } catch (err) {
    chunks.value = []
    notify(err, '加载分块失败')
  } finally {
    chunksLoading.value = false
  }
}

async function reindex(document: KnowledgeDocument): Promise<void> {
  try {
    await adminApi.reindexDocument(document.id)
    ElMessage.success('已提交重建索引')
    await fetchDocuments()
  } catch (err) {
    notify(err, '重建索引失败')
  }
}

async function remove(document: KnowledgeDocument): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `删除「${document.title}」会同时清除它的全部分块与向量，且不可恢复。确认？`,
      '删除文档',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await adminApi.deleteDocument(document.id)
    ElMessage.success('已删除')
    await fetchDocuments()
  } catch (err) {
    notify(err, '删除失败')
  }
}

onMounted(fetchDocuments)
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

    <el-card shadow="never" class="section">
      <template #header>上传文档</template>
      <UploadDropzone :disabled="false" @upload="upload" />
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>
        <div class="head">
          <span>文档列表</span>
          <el-button size="small" @click="fetchDocuments">刷新</el-button>
        </div>
      </template>

      <DocumentTable
        :documents="documents"
        :loading="loading"
        @preview="preview"
        @reindex="reindex"
        @remove="remove"
      />
    </el-card>

    <ChunkPreviewDrawer
      v-model="drawerVisible"
      :document="currentDocument"
      :chunks="chunks"
      :loading="chunksLoading"
      @reindex="reindex"
    />
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
}
</style>

