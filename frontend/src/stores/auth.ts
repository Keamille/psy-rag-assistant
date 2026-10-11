// 认证状态。
//
// 职责边界：api/auth.ts 只负责发请求，令牌的写入与清空都在这里决定。
// 这不是洁癖，而是因为"注销失败时要不要清令牌"是个业务判断，
// 放在传输层会让 api 函数带着副作用，难以复用与测试。

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as authApi from '@/api/auth'
import { ApiError } from '@/api/client'
import { tokenStore } from '@/api/token'
import * as usersApi from '@/api/users'
import type { AuthResult, User } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const ready = ref(false)
  const bootstrapped = ref(false)
  const lastError = ref<string | null>(null)
  const isAuthenticated = computed(() => Boolean(user.value))
  const isAdmin = computed(() => user.value?.role === 'admin')
  const accessToken = computed(() => tokenStore.access)

  function applyAuthResult(result: AuthResult): void {
    tokenStore.set(result.access_token, result.refresh_token)
    user.value = result.user
  }

  async function login(account: string, password: string): Promise<void> {
    lastError.value = null
    try {
      applyAuthResult(await authApi.login({ account, password }))
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : '登录失败'
      throw err
    }
  }

  async function register(payload: authApi.RegisterPayload): Promise<void> {
    lastError.value = null
    try {
      applyAuthResult(await authApi.register(payload))
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : '注册失败'
      throw err
    }
  }

  // 退出登录。
  //
  // 关键判断：服务端撤销失败（503，通常是 Redis 不可用）时**不能**清空本地令牌。
  // 否则用户以为已经退出，而令牌其实还有效——这是安全语义上的欺骗。
  // 此时把异常抛给调用方，由界面提示"退出失败，请稍后重试"。
  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } catch (err) {
      if (err instanceof ApiError && err.httpStatus >= 500) {
        lastError.value = err.message
        throw err
      }
      // 其他情况（令牌本身已失效等）视为已退出，继续清理本地状态
    }
    tokenStore.clear()
    user.value = null
  }

  // 应用启动时恢复登录状态。
  //
  // 这里调 /users/me 而不是直接信任本地令牌：后端会做数据库二次校验，
  // 用户被禁用或删除时即使令牌未过期也会 401，前端据此清掉本地状态。
  async function bootstrap(): Promise<void> {
    if (bootstrapped.value) return

    if (!tokenStore.access) {
      bootstrapped.value = true
      ready.value = true
      return
    }

    try {
      user.value = await usersApi.getMe()
    } catch (err) {
      // 恢复登录状态失败（令牌失效、用户被禁用、后端不可达）一律清掉本地令牌，
      // 让用户重新登录，而不是留着一个用不了的令牌在界面里反复重试。
      tokenStore.clear()
      user.value = null
      lastError.value = err instanceof ApiError ? err.message : '登录状态已失效'
    } finally {
      bootstrapped.value = true
      ready.value = true
    }
  }

  return {
    user,
    ready,
    lastError,
    isAuthenticated,
    isAdmin,
    accessToken,
    login,
    register,
    logout,
    bootstrap,
  }
})

