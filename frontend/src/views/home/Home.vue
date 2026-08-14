<template>
  <div>
    <el-card class="welcome-card" shadow="never">
      <div class="welcome">
        <div>
          <h2 class="brand-font">{{ greeting }}，{{ userStore.user?.name }}！</h2>
          <p class="welcome-sub">欢迎使用蜀道安全助手，统一处理隐患上报、法规问答与安全考试。</p>
        </div>
        <el-avatar :size="56" class="welcome-avatar">{{ (userStore.user?.name || '?').slice(0, 1) }}</el-avatar>
      </div>
    </el-card>

    <el-row :gutter="16" class="module-row">
      <el-col v-for="m in modules" :key="m.path" :xs="24" :sm="12" :lg="8">
        <el-card shadow="hover" class="module-card" @click="router.push(m.path)">
          <div class="module-icon">
            <el-icon :size="30"><component :is="m.icon" /></el-icon>
          </div>
          <div class="module-info">
            <h3>{{ m.title }}</h3>
            <p>{{ m.desc }}</p>
            <el-tag v-if="m.roles && !hasRole(m.roles)" size="small" type="info">管理功能</el-tag>
            <el-button type="primary" link>进入 →</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { ROLE } from '@/types/models/user'

const router = useRouter()
const userStore = useUserStore()

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '凌晨好'
  if (h < 12) return '上午好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

function hasRole(roles?: number[]): boolean {
  return !roles || roles.includes(userStore.roleId)
}

/** 模块入口：图标 + 标题 + 描述区分；磁贴统一黛青单色系（去彩虹模板感） */
const modules = [
  {
    title: '隐患安全管理',
    desc: '现场隐患图片上报与智能识别，列表筛选与闭环跟踪。',
    path: '/hazards',
    icon: 'Warning',
  },
  {
    title: 'AI 智能助手',
    desc: '基于法规知识库的法规问答，答案附依据来源，可查看原文。',
    path: '/ai/assistant',
    icon: 'ChatDotRound',
  },
  {
    title: '考试工坊',
    desc: '题库管理、组卷发布与在线考试，自动阅卷出成绩。',
    path: '/exams',
    icon: 'Tickets',
  },
  {
    title: '题库管理',
    desc: '维护单选题/多选题/判断题/填空题题库，支撑组卷与考试。',
    path: '/exam/questions',
    icon: 'Collection',
    roles: [ROLE.SAFETY, ROLE.ADMIN],
  },
  {
    title: 'AI 出题',
    desc: '按知识点与题型批量生成题目，批次审核、重写与统计。',
    path: '/exam/ai/generate',
    icon: 'MagicStick',
    roles: [ROLE.SAFETY, ROLE.ADMIN],
  },
  {
    title: '试卷管理',
    desc: '手动/智能组卷，配置时长与合格线，发布后开放考试。',
    path: '/exam/papers',
    icon: 'DocumentChecked',
    roles: [ROLE.SAFETY, ROLE.ADMIN],
  },
]
</script>

<style scoped>
.welcome-card {
  margin-bottom: 16px;
}
.welcome {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.welcome h2 {
  margin: 0 0 8px;
  font-size: 20px;
  color: var(--el-text-color-primary, #232b2a);
}
.welcome-sub {
  margin: 0;
  color: var(--el-text-color-secondary, #707a78);
}
.welcome-avatar {
  background-color: var(--el-color-primary, #1e5a52);
  color: #fff;
  font-size: 24px;
  flex-shrink: 0;
}
.module-row {
  margin-top: 16px;
}
.module-card {
  cursor: pointer;
  margin-bottom: 16px;
}
.module-card :deep(.el-card__body) {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.module-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--brand-soft, #e6efed);
  color: var(--brand, #1e5a52);
}
.module-info {
  flex: 1;
}
.module-info h3 {
  margin: 0 0 6px;
  font-size: 16px;
  color: var(--el-text-color-primary, #232b2a);
}
.module-info p {
  margin: 0 0 8px;
  color: var(--el-text-color-secondary, #707a78);
  font-size: 13px;
  line-height: 1.6;
}
</style>
