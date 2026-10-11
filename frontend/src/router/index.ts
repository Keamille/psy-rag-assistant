/** 路由与守卫（开发文档 11.1）。 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/chat' },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true, layout: 'blank', title: '登录' },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { public: true, layout: 'blank', title: '注册' },
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '对话' },
  },
  {
    path: '/chat/:id(\\d+)',
    name: 'chat-detail',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '对话' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '设置' },
  },
  {
    path: '/admin/documents',
    name: 'admin-documents',
    component: () => import('@/views/admin/DocumentsView.vue'),
    meta: { requiresAdmin: true, title: '知识库管理' },
  },
  {
    path: '/admin/crisis',
    name: 'admin-crisis',
    component: () => import('@/views/admin/CrisisView.vue'),
    meta: { requiresAdmin: true, title: '危机事件' },
  },
  {
    path: '/admin/config',
    name: 'admin-config',
    component: () => import('@/views/admin/ConfigView.vue'),
    meta: { requiresAdmin: true, title: '参数配置' },
  },
  {
    path: '/admin/stats',
    name: 'admin-stats',
    component: () => import('@/views/admin/StatsView.vue'),
    meta: { requiresAdmin: true, title: '概览统计' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { public: true, layout: 'blank', title: '页面不存在' },
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.bootstrap()

  const isPublic = Boolean(to.meta.public)
  if (!isPublic && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (isPublic && auth.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
    return { name: 'chat' }
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'chat' }
  }
  return true
})

router.afterEach((to) => {
  const title = (to.meta.title as string | undefined) ?? ''
  document.title = title ? `${title} · 心理咨询 AI 助手` : '心理咨询 AI 助手'
})

export default router

