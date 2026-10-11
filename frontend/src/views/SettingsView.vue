<script setup lang="ts">
// 个人设置（开发文档 §11.4）。数据与操作都走 api/users.ts。

import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { ApiError } from '@/api/client'
import { deleteMyData, exportMyData, updatePassword } from '@/api/users'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const changing = ref(false)
const form = reactive({ old_password: '', password: '' })

const profile = computed(() => auth.user)

function notify(err: unknown, fallback: string): void {
  if (err instanceof ApiError) {
    ElMessage.warning(err.message)
  } else {
    ElMessage.warning(fallback)
  }
}

async function changePassword(): Promise<void> {
  if (!form.old_password || !form.password) {
    ElMessage.warning('请填写原密码与新密码')
    return
  }
  changing.value = true
  try {
    await updatePassword({ old_password: form.old_password, password: form.password })
    ElMessage.success('密码已更新，其他设备需要重新登录')
    form.old_password = ''
    form.password = ''
  } catch (err) {
    notify(err, '修改失败')
  } finally {
    changing.value = false
  }
}

async function exportData(): Promise<void> {
  try {
    const blob = await exportMyData()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'my-data.json'
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    notify(err, '导出失败')
  }
}

async function deleteAll(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '将删除你的全部会话数据且不可恢复（备份轮转期内仍可能存在）。确认继续？',
      '删除全部数据',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteMyData({ scope: 'all', password: '' })
    ElMessage.success('已提交删除请求')
  } catch (err) {
    notify(err, '删除失败')
  }
}
</script>

<template>
  <div class="settings">
    <el-card shadow="never">
      <template #header>账号信息</template>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="用户名">{{ profile?.username ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ profile?.email ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="角色">
          {{ profile?.role === 'admin' ? '管理员' : '普通用户' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>修改密码</template>
      <el-form label-width="90px" style="max-width: 440px">
        <el-form-item label="原密码">
          <el-input v-model="form.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-button type="primary" :loading="changing" @click="changePassword">保存</el-button>
      </el-form>
      <div class="psy-hint tip">
        改密码后当前 refresh 令牌会被撤销，效果等同于踢掉其他已登录设备。
        如果后端返回 revoked_current_token: false，说明撤销没成功（通常是 Redis 不可用），
        此时密码已改成功，但其他设备可能仍处于登录状态。
      </div>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header>数据与隐私</template>
      <p class="psy-hint">
        对话内容默认保留 180 天，危机事件保留 365 天。删除后 7 天内仍可能从备份恢复，
        之后随备份轮转清除。
      </p>
      <div class="actions">
        <el-button @click="exportData">导出我的数据</el-button>
        <el-button type="danger" plain @click="deleteAll">删除全部数据</el-button>
      </div>
      <div class="psy-hint tip">
        导出为 JSON 文件，包含你的全部会话与消息；删除为软删除，
        界面上不可见但备份轮转期内仍可能存在于备份中。
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.settings {
  padding: 16px;
  overflow-y: auto;
}

.section {
  margin-top: 16px;
}

.tip {
  margin-top: 10px;
  line-height: 1.8;
}

.actions {
  display: flex;
  gap: 10px;
}
</style>

