<script setup lang="ts">
// 参数配置（开发文档 §7.7）。
// 可调参数存在 Redis 覆盖层里，重启后仍生效；不可在线改的键必须改环境变量后重启。

import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import * as adminApi from '@/api/admin'
import { ApiError } from '@/api/client'
import type { AdminConfig } from '@/api/types'

const config = ref<AdminConfig | null>(null)
const loading = ref(false)
const hint = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    config.value = await adminApi.getConfig()
    hint.value = `配置来源：${config.value.source}`
  } catch (err) {
    hint.value = err instanceof ApiError ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!config.value) return
  try {
    await adminApi.updateConfig(config.value.values)
    ElMessage.success('已保存')
  } catch (err) {
    ElMessage.warning(err instanceof ApiError ? err.message : '保存失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="page" v-loading="loading">
    <el-alert v-if="hint" class="section" type="info" :closable="false" show-icon :title="hint" />

    <el-card v-if="config" shadow="never">
      <template #header>
        <div class="head">
          <span>可在线调整的参数</span>
          <div class="ops">
            <el-button size="small" @click="load">重置</el-button>
            <el-button type="primary" size="small" @click="save">保存</el-button>
          </div>
        </div>
      </template>

      <el-form label-width="190px" style="max-width: 560px">
        <el-form-item label="召回条数 top_k_retrieve">
          <el-input-number v-model="config.values.top_k_retrieve" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="重排保留 top_k_rerank">
          <el-input-number v-model="config.values.top_k_rerank" :min="1" :max="20" />
        </el-form-item>
        <el-form-item label="启用重排 rerank_enabled">
          <el-switch v-model="config.values.rerank_enabled" />
        </el-form-item>
        <el-form-item label="温度 llm_temperature">
          <el-input-number
            v-model="config.values.llm_temperature"
            :min="0"
            :max="1"
            :step="0.1"
          />
        </el-form-item>
        <el-form-item label="最大输出 llm_max_tokens">
          <el-input-number
            v-model="config.values.llm_max_tokens"
            :min="128"
            :max="4096"
            :step="128"
          />
        </el-form-item>
        <el-form-item label="日配额 daily_message_quota">
          <el-input-number v-model="config.values.daily_message_quota" :min="1" :max="10000" />
        </el-form-item>
        <el-form-item label="热线区域 hotline_region">
          <el-input v-model="config.values.hotline_region" />
        </el-form-item>
      </el-form>

      <el-divider />
      <div class="psy-hint">
        需改环境变量并重启（不可在线调整）：{{ config.restart_required_keys.join('、') }}
      </div>
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
}

.ops {
  display: flex;
  gap: 8px;
}
</style>

