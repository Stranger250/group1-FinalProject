<template>
  <el-aside :width="appStore.collapsed ? '64px' : '224px'" class="app-sidebar">
    <div class="logo" @click="router.push('/home')">
      <div class="logo-seal" aria-hidden="true">蜀</div>
      <div v-show="!appStore.collapsed" class="logo-text">
        <span class="logo-title brand-font">蜀道安全助手</span>
        <span class="logo-sub">SHUDAO SAFETY</span>
      </div>
    </div>
    <div v-show="!appStore.collapsed" class="sidebar-motto brand-font">山路千重 · 安全为纲</div>
    <el-scrollbar class="menu-scroll">
      <el-menu
        :default-active="activePath"
        :collapse="appStore.collapsed"
        :collapse-transition="false"
        router
      >
        <template v-for="group in menu" :key="group.title">
          <!-- 单入口组：直接渲染菜单项 -->
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
    <div v-show="!appStore.collapsed" class="sidebar-foot">
      <span class="foot-ver">v0.1 · 实训交付</span>
    </div>
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

/** 高亮路径：精确匹配优先；子页面回退到最长前缀菜单 */
const activePath = computed(() => {
  const path = route.path
  if (menuPaths.value.includes(path)) return path
  const prefix = menuPaths.value.filter((p) => path.startsWith(p)).sort((a, b) => b.length - a.length)[0]
  return prefix ?? path
})
</script>

<style scoped>
.app-sidebar {
  background-color: var(--brand-deep, #101d1b);
  transition: width 0.2s;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(255, 253, 248, 0.06);
}
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  cursor: pointer;
  flex-shrink: 0;
}
.logo-seal {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-serif);
  font-size: 17px;
  color: #fdf6ec;
  background: var(--cinnabar, #b43a2c);
  border-radius: 4px;
  flex-shrink: 0;
}
.logo-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.logo-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #f4efe2;
  white-space: nowrap;
}
.logo-sub {
  margin-top: 3px;
  font-size: 9px;
  letter-spacing: 0.22em;
  color: #5d7d77;
  white-space: nowrap;
}
.sidebar-motto {
  padding: 0 18px 10px;
  font-size: 12px;
  letter-spacing: 0.3em;
  color: #4c6a64;
  text-align: center;
  border-bottom: 1px solid rgba(255, 253, 248, 0.06);
  margin-bottom: 6px;
  flex-shrink: 0;
  white-space: nowrap;
  overflow: hidden;
}
.menu-scroll {
  flex: 1;
}
.sidebar-foot {
  padding: 12px 0;
  text-align: center;
  font-size: 11px;
  letter-spacing: 0.14em;
  color: #41605a;
  flex-shrink: 0;
}
/* 内缩式导航：黛青胶囊激活 */
:deep(.el-menu) {
  border-right: none;
  padding: 6px 8px;
}
:deep(.el-menu-item),
:deep(.el-sub-menu__title) {
  border-radius: 4px;
  margin-bottom: 2px;
  font-size: 13px;
  letter-spacing: 0.03em;
}
:deep(.el-menu-item:hover),
:deep(.el-sub-menu__title:hover) {
  background-color: var(--el-menu-hover-bg-color, #182b28);
}
:deep(.el-menu-item.is-active) {
  background-color: var(--brand, #1e5a52);
  color: #fffdf8;
}
:deep(.el-sub-menu .el-menu-item) {
  padding-left: 46px !important;
  font-size: 12.5px;
}
</style>
