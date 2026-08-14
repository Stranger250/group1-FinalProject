<template>
  <el-header class="app-header">
    <div class="header-left">
      <el-icon class="collapse-btn" :size="20" @click="appStore.toggleCollapse()">
        <Expand v-if="appStore.collapsed" />
        <Fold v-else />
      </el-icon>
      <span class="page-title">{{ route.meta.title || '' }}</span>
    </div>
    <div class="header-right">
      <el-dropdown trigger="click" @command="onCommand">
        <span class="user-trigger">
          <el-avatar :size="30" class="user-avatar" :src="userStore.user?.avatar || undefined">
            {{ (userStore.user?.name || '?').slice(0, 1) }}
          </el-avatar>
          <span class="user-name">{{ userStore.user?.name || userStore.user?.username }}</span>
          <el-icon><ArrowDown /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              {{ userStore.user?.name }} · {{ roleName(userStore.roleId) }}
            </el-dropdown-item>
            <el-dropdown-item divided command="profile">
              <el-icon><User /></el-icon>个人中心
            </el-dropdown-item>
            <el-dropdown-item command="logout">
              <el-icon><SwitchButton /></el-icon>退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </el-header>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAppStore } from '@/store/app'
import { useUserStore } from '@/store/user'
import { roleName } from '@/types/models/user'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

async function onCommand(cmd: string) {
  if (cmd === 'profile') {
    router.push('/profile')
    return
  }
  if (cmd !== 'logout') return
  await ElMessageBox.confirm('确定退出登录吗？', '提示', { type: 'warning' })
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: #fff;
  box-shadow: 0 1px 0 var(--el-border-color-lighter, #ece8df), 0 2px 8px rgba(23, 45, 43, 0.05);
  padding: 0 16px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.collapse-btn {
  cursor: pointer;
  color: #606266;
}
.collapse-btn:hover {
  color: var(--el-color-primary, #1e5a52);
}
.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.header-right {
  display: flex;
  align-items: center;
}
.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #303133;
  outline: none;
}
.user-avatar {
  background-color: var(--el-color-primary, #1e5a52);
  color: #fff;
  font-size: 14px;
}
.user-name {
  font-size: 14px;
}
</style>
