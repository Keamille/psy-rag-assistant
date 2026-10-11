<script setup lang="ts">
/** 应用外壳：左侧导航 + 主内容区。移动端导航收进抽屉。 */

import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const drawerVisible = ref(false)

const navItems = computed(() => {
  const items = [
    { name: 'chat', label: '对话' },
    { name: 'settings', label: '设置' },
  ]
  if (auth.isAdmin) {
    items.push(
      { name: 'admin-documents', label: '知识库' },
      { name: 'admin-crisis', label: '危机事件' },
      { name: 'admin-stats', label: '概览' },
      { name: 'admin-config', label: '参数' },
    )
  }
  return items
})

/** 切路由时自动收起抽屉，避免移动端抽屉挡住新页面 */
watch(
  () => route.fullPath,
  () => {
    drawerVisible.value = false
  },
)

async function handleLogout(): Promise<void> {
  try {
    await auth.logout()
    router.push({ name: 'login' })
  } catch (err) {
    // 注销失败（通常是 Redis 不可用）时不清空本地令牌，
    // 让用户知道"还没退出"，而不是以为退出了其实令牌还有效
    ElMessage.error(err instanceof ApiError ? err.message : '退出失败，请稍后重试')
  }
}

</script>

<template>
  <div class="layout">
    <aside class="sidebar" aria-label="主导航">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">心</span>
        <div class="brand-text">
          <div class="brand-name">心理咨询 AI 助手</div>
          <div class="psy-hint">情绪支持与心理学知识科普</div>
        </div>
      </div>

      <nav class="nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-item"
        >
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div class="user-line">
          <span class="user-name">{{ auth.user?.username ?? '未登录' }}</span>
          <el-tag v-if="auth.isAdmin" size="small" effect="plain">管理员</el-tag>
        </div>
        <el-button text size="small" @click="handleLogout">退出</el-button>
      </div>
    </aside>

    <main class="content">
      <header class="topbar">
        <el-button
          class="menu-btn"
          text
          aria-label="打开导航"
          @click="drawerVisible = true"
        >
          ☰
        </el-button>
        <span class="topbar-title">{{ route.meta.title ?? '' }}</span>
      </header>

      <slot />
    </main>

    <!-- 移动端导航抽屉 -->
    <el-drawer v-model="drawerVisible" direction="ltr" size="240px" :with-header="false">
      <nav class="drawer-nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="drawer-item"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
    </el-drawer>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  display: flex;
  flex-direction: column;
  width: 232px;
  flex: 0 0 232px;
  padding: 16px 12px;
  background: var(--psy-panel);
  border-right: 1px solid var(--psy-border);
}

.brand {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 4px 6px 16px;
}

.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  border-radius: 8px;
  background: var(--psy-primary);
  color: #fff;
  font-size: 16px;
}

.brand-text {
  min-width: 0;
}

.brand-name {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.nav-item {
  padding: 8px 10px;
  border-radius: 6px;
  color: var(--psy-text-soft);
  text-decoration: none;
}

.nav-item:hover {
  background: #f0f2f5;
}

.nav-item.router-link-active {
  background: #eef2f8;
  color: var(--psy-primary);
  font-weight: 600;
}

.sidebar-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid var(--psy-border);
}

.user-line {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.user-name {
  max-width: 84px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.content {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.topbar {
  display: none;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--psy-panel);
  border-bottom: 1px solid var(--psy-border);
}

.topbar-title {
  font-weight: 600;
}

.menu-btn {
  font-size: 18px;
}

.drawer-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.drawer-item {
  padding: 10px 12px;
  border-radius: 6px;
  color: var(--psy-text-soft);
  text-decoration: none;
}

.drawer-item.router-link-active {
  background: #eef2f8;
  color: var(--psy-primary);
  font-weight: 600;
}

@media (max-width: 767px) {
  .sidebar {
    display: none;
  }

  .topbar {
    display: flex;
  }
}
</style>

