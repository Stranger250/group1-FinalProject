<template>
  <el-aside :width="appStore.collapsed ? '64px' : '220px'" class="app-sidebar">
    <div class="logo" @click="router.push('/home')">
      <el-icon :size="26" class="logo-icon"><Umbrella /></el-icon>
      <span v-show="!appStore.collapsed" class="logo-title brand-font">蜀道安全助手</span>
    </div>
    <el-scrollbar class="menu-scroll">
      <el-menu
        :default-active="activePath"
        :collapse="appStore.collapsed"
        :collapse-transition="false"
        router
      >
        <template v-for="group in menu" :key="group.title">
          <!-- 单入口组：直接渲染菜单项（如 首页） -->
          <el-menu-item v-if="group.children.length === 1" :index="group.children[0].path">
            <el-icon><component :is="group.children[0].icon || group.icon || 'Menu'" /></el-icon>
            <template #title>{{ group.children[0].title }}</template>
          </el-menu-item>
          <!-- 多入口组：子菜单 -->
          <el-sub-menu v-else :index="group.title">
            <template #title>
              <el-icon><component :is="group.icon || 'Folder'" /></el-icon>
              <span>{{ group.title }}</span>
            </template>
            <el-menu-item v-for="item in group.children" :key="item.path" :index="item.path">
              <el-icon><component :is="item.icon || 'Document'" /></el-icon>
              <template #title>{{ item.title }}</template>
            </el-menu-item>
          </el-sub-menu>
        </template>
      </el-menu>
    </el-scrollbar>
  </el-aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/store/app'
import { useUserStore } from '@/store/user'
import { buildMenu } from '@/router/menu'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

const menu = computed(() => buildMenu(userStore.roleId))

const menuPaths = computed(() => menu.value.flatMap((g) => g.children.map((c) => c.path)))

/** 高亮路径：精确匹配优先；子页面（详情/作答等 hidden 路由）回退到最长前缀菜单 */
const activePath = computed(() => {
  const path = route.path
  if (menuPaths.value.includes(path)) return path
  const prefix = menuPaths.value.filter((p) => path.startsWith(p)).sort((a, b) => b.length - a.length)[0]
  return prefix ?? path
})
</script>

<style scoped>
.app-sidebar {
  background-color: var(--brand-deep, #102a28);
  transition: width 0.2s;
  display: flex;
  flex-direction: column;
}
.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  color: #fff;
  flex-shrink: 0;
}
.logo-icon {
  color: var(--el-color-primary-light-3, #4c7f77);
}
.logo-title {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}
.menu-scroll {
  flex: 1;
}
/* 内缩式导航：留出边距让激活项呈现「黛青胶囊」 */
:deep(.el-menu) {
  border-right: none;
  padding: 8px;
}
:deep(.el-menu-item),
:deep(.el-sub-menu__title) {
  border-radius: 6px;
  margin-bottom: 2px;
}
:deep(.el-menu-item:hover),
:deep(.el-sub-menu__title:hover) {
  background-color: var(--el-menu-hover-bg-color, #1a3b38);
}
/* 激活项：黛青实底 + 白字，替代默认高亮 */
:deep(.el-menu-item.is-active) {
  background-color: var(--el-color-primary, #1e5a52);
  color: #fff;
}
</style>
