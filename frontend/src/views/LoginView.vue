<script setup lang="ts">
// 登录页（开发文档 §11.1）。

import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const form = reactive({ account: '', password: '' })
const submitting = ref(false)

async function submit(): Promise<void> {
  if (!form.account || !form.password) {
    ElMessage.warning('请填写账号和密码')
    return
  }
  submitting.value = true
  try {
    await auth.login(form.account, form.password)
    ElMessage.success('登录成功')
    // 登录前的目标页会被记在 query 里，登录后回到那里
    router.push((route.query.redirect as string) ?? { name: 'chat' })
  } catch (err) {
    if (err instanceof ApiError && err.isRateLimited) {
      ElMessage.warning(`尝试过于频繁，请等待 ${err.retryAfter ?? 60} 秒后再试`)
    } else {
      ElMessage.error(err instanceof Error ? err.message : '登录失败')
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="brand-panel">
      <div class="logo" aria-hidden="true">心</div>
      <h1>心理咨询 AI 助手</h1>
      <p class="slogan">提供情绪支持与心理学知识科普</p>
      <ul class="points">
        <li>回答基于自有知识库，可点开查看原文出处</li>
        <li>不会给出诊断结论，也不提供用药建议</li>
        <li>识别到风险时会先请你联系专业求助渠道</li>
      </ul>
    </div>

    <el-card class="auth-card" shadow="never">
      <div class="card-title">登录</div>

      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="账号或邮箱">
          <el-input
            v-model="form.account"
            placeholder="用户名或邮箱"
            autocomplete="username"
            aria-label="账号或邮箱"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
            aria-label="密码"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" class="full" :loading="submitting" @click="submit">
          登录
        </el-button>
      </el-form>

      <div class="foot">
        <RouterLink to="/register">还没有账号？去注册</RouterLink>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.auth-page {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 48px;
  min-height: 100vh;
  padding: 24px;
  background: linear-gradient(160deg, #f5f7fb 0%, #eef2f8 100%);
}

.brand-panel {
  max-width: 360px;
}

.logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--psy-radius-lg);
  background: var(--psy-primary);
  color: #fff;
  font-size: 24px;
  margin-bottom: 16px;
}

.brand-panel h1 {
  margin: 0 0 8px;
  font-size: 24px;
}

.slogan {
  margin: 0 0 20px;
  color: var(--psy-text-soft);
}

.points {
  padding-left: 18px;
  margin: 0;
  color: var(--psy-text-soft);
  font-size: 13px;
  line-height: 2;
}

.auth-card {
  width: 400px;
  max-width: 100%;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 16px;
}

.full {
  width: 100%;
}

.foot {
  margin-top: 14px;
  font-size: 13px;
}

@media (max-width: 860px) {
  .auth-page {
    flex-direction: column;
    gap: 24px;
  }

  .brand-panel {
    text-align: center;
  }

  .points {
    display: none;
  }
}
</style>

