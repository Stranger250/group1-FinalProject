<template>
  <div class="page-container home-page">
    <!-- 碑首：问候 + 题跋 -->
    <div class="home-head">
      <div class="head-main">
        <span class="head-kicker brand-font">蜀道安全 · 运维台</span>
        <h2 class="head-title">{{ greeting }}，{{ userStore.user?.name }}</h2>
      </div>
      <div class="head-seal" aria-hidden="true">安</div>
    </div>

    <!-- 主模块路碑（三大模块，编号 + 题跋式） -->
    <div class="stele-row">
      <div v-for="(m, i) in mainModules" :key="m.path" class="stele" @click="router.push(m.path)">
        <div class="stele-no brand-font">{{ String(i + 1).padStart(2, '0') }}</div>
        <div class="stele-body">
          <h3 class="stele-title brand-font">{{ m.title }}</h3>
          <p class="stele-desc">{{ m.desc }}</p>
          <div class="stele-foot">
            <span class="stele-path">{{ m.path }}</span>
            <span class="stele-enter">进 →</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 管理侧路碑（角色可见） -->
    <div v-if="manageModules.length" class="manage-block">
      <div class="manage-head section-title">
        <span class="st-main brand-font">管理工坊</span>
        <span class="st-sub">题 · 卷 · 审 · 统</span>
      </div>
      <div class="manage-row">
        <div v-for="m in manageModules" :key="m.path" class="manage-item" @click="router.push(m.path)">
          <el-icon :size="18" class="manage-icon"><component :is="m.icon" /></el-icon>
          <span class="manage-title">{{ m.title }}</span>
          <span class="manage-arrow">›</span>
        </div>
      </div>
    </div>
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

/** 三大主模块（路碑） */
const mainModules = [
  {
    title: '隐患安全管理',
    desc: '现场隐患图片上报与智能识别，列表筛选与闭环跟踪。',
    path: '/hazards',
  },
  {
    title: 'AI 智能助手',
    desc: '基于法规知识库的法规问答，答案附依据来源，可查看原文。',
    path: '/ai/assistant',
  },
  {
    title: '考试工坊',
    desc: '题库管理、组卷发布与在线考试，自动阅卷出成绩。',
    path: '/exams',
  },
]

/** 管理侧模块（题/卷/审/统，按角色过滤） */
const manageModules = [
  {
    title: '题库管理',
    path: '/exam/questions',
    icon: 'Collection',
    roles: [ROLE.SAFETY, ROLE.ADMIN],
  },
  {
    title: 'AI 出题',
    path: '/exam/ai/generate',
    icon: 'MagicStick',
    roles: [ROLE.SAFETY, ROLE.ADMIN],
  },
  {
    title: '试卷管理',
    path: '/exam/papers',
    icon: 'DocumentChecked',
    roles: [ROLE.SAFETY, ROLE.ADMIN],
  },
  {
    title: '考试统计',
    path: '/exams/stats',
  },
  {
    title: '我的错题',
    path: '/exams/wrong-book',
  },
].filter((m) => hasRole(m.roles))
</script>

<style scoped>
.home-page {
  max-width: 1080px;
  margin: 0 auto;
}

/* 碑首 */
.home-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding: 26px 4px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 26px;
}
.head-kicker {
  display: block;
  font-size: 13px;
  letter-spacing: 0.34em;
  color: var(--brand);
  margin-bottom: 10px;
}
.head-title {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink);
}
.head-seal {
  width: 46px;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-serif);
  font-size: 22px;
  color: #fdf6ec;
  background: var(--cinnabar);
  border-radius: 5px;
  box-shadow: 0 2px 6px rgba(120, 40, 30, 0.3);
}

/* 三大路碑 */
.stele-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
}
.stele {
  display: flex;
  gap: 16px;
  padding: 22px 20px;
  background: var(--paper);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  box-shadow: var(--shadow-card);
}
.stele:hover {
  transform: translateY(-2px);
  box-shadow: 0 3px 10px rgba(60, 50, 20, 0.08), 0 8px 24px rgba(60, 50, 20, 0.1);
  border-color: var(--el-border-color);
}
.stele-no {
  flex-shrink: 0;
  font-size: 34px;
  font-weight: 700;
  line-height: 1;
  color: var(--brand-soft);
  -webkit-text-stroke: 1px var(--brand);
  padding-top: 2px;
}
.stele-body {
  flex: 1;
}
.stele-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--ink);
}
.stele-desc {
  margin: 0 0 14px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-secondary);
}
.stele-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.stele-path {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.stele-enter {
  font-size: 13px;
  letter-spacing: 0.1em;
  color: var(--brand);
}

/* 管理工坊 */
.manage-block {
  margin-top: 34px;
}
.manage-head {
  margin-bottom: 12px;
}
.manage-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}
.manage-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 16px;
  background: var(--paper);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 5px;
  cursor: pointer;
  transition: border-color 0.12s ease, background 0.12s ease;
}
.manage-item:hover {
  border-color: var(--brand);
  background: #f6f3e6;
}
.manage-icon {
  color: var(--brand);
  flex-shrink: 0;
}
.manage-title {
  flex: 1;
  font-size: 14px;
  letter-spacing: 0.05em;
  color: var(--ink);
}
.manage-arrow {
  color: var(--el-text-color-placeholder);
  font-size: 16px;
}

@media (max-width: 900px) {
  .stele-row {
    grid-template-columns: 1fr;
  }
}
</style>
