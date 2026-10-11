<script setup lang="ts">
// 注册页（开发文档 §11.1 / §10.4）。
//
// 合规要点：年龄确认与知情同意必须由用户主动勾选，后端也会独立校验一遍——
// 前端的拦截只是体验，不是防线。
//
// consent_version 必须从 /meta/config 取，绝不能写死：
// 免责声明升级后，前端让用户同意 v1.0、后端校验 v2.0，注册会永久失败。

import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ApiError } from '@/api/client'
import { systemApi } from '@/api/system'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const form = reactive({
  email: '',
  username: '',
  password: '',
  age_confirmed: false,
  consent: false,
})
const submitting = ref(false)
const consentVersion = ref('')
const versionLoading = ref(true)

const passwordHint = computed(() => {
  const pwd = form.password
  if (!pwd) return ''
  if (pwd.length < 10) return '至少 10 位'
  if (!/[A-Za-z]/.test(pwd)) return '需要包含字母'
  if (!/\d/.test(pwd)) return '需要包含数字'
  return '密码强度符合要求'
})
const passwordOk = computed(() => passwordHint.value === '密码强度符合要求')

async function loadConsentVersion(): Promise<void> {
  versionLoading.value = true
  try {
    const config = await systemApi.metaConfig()
    consentVersion.value = config.disclaimer_version
  } catch {
    consentVersion.value = ''
  } finally {
    versionLoading.value = false
  }
}

async function submit(): Promise<void> {
  if (!form.email || !form.username || !form.password) {
    ElMessage.warning('请完整填写注册信息')
    return
  }
  if (!passwordOk.value) {
    ElMessage.warning(`密码不符合要求：${passwordHint.value}`)
    return
  }
  if (!form.age_confirmed || !form.consent) {
    ElMessage.warning('需确认年满 18 周岁并同意知情同意书')
    return
  }
  if (!consentVersion.value) {
    ElMessage.error('未能取得知情同意书版本，请稍后重试或联系管理员')
    return
  }

  submitting.value = true
  try {
    await auth.register({ ...form, consent_version: consentVersion.value })
    ElMessage.success('注册成功')
    router.push({ name: 'chat' })
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '注册失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadConsentVersion)
</script>

<template>
  <div class="auth-page">
    <el-card class="auth-card" shadow="never">
      <div class="card-title">创建账号</div>
      <div class="psy-hint">本助手仅面向 18 岁以上成年人开放</div>

      <el-form label-position="top" class="form">
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="user@example.com" aria-label="邮箱" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="3-64 个字符，用于登录与展示" aria-label="用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="至少 10 位，含字母与数字"
            aria-label="密码"
          />
          <div v-if="passwordHint" class="psy-hint hint" :class="{ ok: passwordOk }">
            {{ passwordHint }}
          </div>
        </el-form-item>

        <div class="agreements">
          <el-checkbox v-model="form.age_confirmed">我已年满 18 周岁</el-checkbox>
          <el-checkbox v-model="form.consent">
            我已阅读并同意知情同意书（非医疗服务、数据如何使用、危机时可能的人工介入）
          </el-checkbox>
        </div>

        <el-alert
          v-if="consentVersion"
          type="info"
          :closable="false"
          show-icon
          :title="`当前知情同意书版本：${consentVersion}`"
        />
        <el-alert
          v-else-if="!versionLoading"
          type="error"
          :closable="false"
          show-icon
          title="无法取得知情同意书版本，注册暂不可用"
          description="请确认后端服务可访问（GET /meta/config），或联系管理员。"
        />

        <el-button
          type="primary"
          class="full"
          :loading="submitting"
          :disabled="!consentVersion"
          @click="submit"
        >
          注册
        </el-button>
      </el-form>

      <div class="foot">
        <RouterLink to="/login">已有账号？去登录</RouterLink>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.auth-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background: linear-gradient(160deg, #f5f7fb 0%, #eef2f8 100%);
}

.auth-card {
  width: 520px;
  max-width: 100%;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
}

.form {
  margin-top: 16px;
}

.hint {
  margin-top: 4px;
  color: var(--psy-warning);
}

.hint.ok {
  color: var(--psy-success);
}

.agreements {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.full {
  width: 100%;
  margin-top: 14px;
}

.foot {
  margin-top: 14px;
  font-size: 13px;
}
</style>

