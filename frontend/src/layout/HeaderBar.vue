<template>
  <el-header class="app-header">
    <div class="header-left">
      <el-icon class="collapse-btn" :size="20" @click="appStore.toggleCollapse()">
        <Expand v-if="appStore.collapsed" />
        <Fold v-else />
      </el-icon>
      <div class="page-title-wrap">
        <span class="page-title brand-font">{{ route.meta.title || '' }}</span>
        <span class="page-crumb">{{ route.meta.menu ? '' : crumb }}</span>
      </div>
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
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAppStore } from '@/store/app'
import { useUserStore } from '@/store/user'
import { roleName } from '@/types/models/user'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

/** 面包屑：父路由标题（如 /hazards/report → 隐患管理 / 隐患上报） */
const crumb = computed(() => {
  const full = route.path
  const seg = full.split('/').filter(Boolean)
  if (seg.length <= 1) return ''
  const parentMap: Record<string, string> = {
    hazards: '隐患管理',
    'ai/assistant': 'AI 助手',
    exams: '考试中心',
    'exam/questions': '题库管理',
    'exam/ai': 'AI 出题',
    'exam/papers': '试卷管理',
    profile: '个人中心',
    admin: '系统管理',
  }
  return parentMap[seg.slice(0, 2).join('/')] || parentMap[seg[0]] || ''
})

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
  background-color: var(--paper, #fffdf8);
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 0 18px;
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
  color: var(--brand, #1e5a52);
}
.page-title-wrap {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--ink, #262b28);
}
.page-crumb {
  font-size: 12px;
  letter-spacing: 0.1em;
  color: var(--el-text-color-placeholder);
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
  background-color: var(--brand, #1e5a52);
  color: #fffdf8;
  font-size: 14px;
}
.user-name {
  font-size: 14px;
}
</style>
