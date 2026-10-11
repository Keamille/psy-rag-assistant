<script setup lang="ts">
/**
 * 文档上传区（开发文档 §7.7 / §8.2）。
 *
 * 版权提示与勾选确认是**必须保留**的：项目文档里写明"上传第三方受版权保护
 * 材料的合规责任由运营方承担"，这道拦截是给运营方留的证据链。
 */

import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'

const props = withDefaults(
  defineProps<{ disabled?: boolean; maxSizeMB?: number }>(),
  { disabled: false, maxSizeMB: 50 },
)

const emit = defineEmits<{ upload: [options: UploadRequestOptions] }>()

const copyrightAccepted = ref(false)

function beforeUpload(file: File): boolean {
  if (!copyrightAccepted.value) {
    ElMessage.warning('请先确认你拥有该文档的使用授权')
    return false
  }
  const sizeMB = file.size / 1024 / 1024
  if (sizeMB > props.maxSizeMB) {
    ElMessage.warning(`文件超过 ${props.maxSizeMB} MB 上限`)
    return false
  }
  return true
}
</script>

<template>
  <div class="dropzone">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="版权提示"
      description="请勿上传未获授权的受版权保护书籍全文。上传第三方材料的合规责任由运营方承担。"
    />

    <el-checkbox v-model="copyrightAccepted" class="agree">
      我确认对所上传文档拥有使用授权
    </el-checkbox>

    <el-upload
      drag
      :multiple="false"
      :show-file-list="false"
      :disabled="disabled"
      :before-upload="beforeUpload"
      :http-request="(options: UploadRequestOptions) => emit('upload', options)"
      accept=".pdf,.docx,.md,.txt"
    >
      <div class="hint-main">把文件拖到这里，或点击选择</div>
      <div class="psy-hint">支持 PDF / Word / Markdown / 纯文本，单文件不超过 {{ maxSizeMB }} MB</div>
    </el-upload>
  </div>
</template>

<style scoped>
.dropzone {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agree {
  margin: 0;
}

.hint-main {
  font-size: 14px;
  margin-bottom: 4px;
}
</style>

