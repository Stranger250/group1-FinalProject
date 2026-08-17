import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'

/**
 * 路由表（FRONTEND.md §3 唯一真源）。
 * 注意 Vue Router 4 路径排序：静态段（exams/records、hazards/report）优先于动态段（:recordId、:id），无冲突。
 */
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: () => import('@/layout/index.vue'),
    redirect: '/home',
    children: [
      { path: 'home', name: 'Home', component: () => import('@/views/home/Home.vue'), meta: { title: '首页' } },

      // 模块一 隐患管理
      { path: 'hazards', name: 'HazardList', component: () => import('@/views/hazard/HazardList.vue'), meta: { title: '隐患列表' } },
      { path: 'hazards/report', name: 'HazardReport', component: () => import('@/views/hazard/HazardReport.vue'), meta: { title: '隐患上报' } },
      { path: 'hazards/analyze', name: 'HazardAnalyze', component: () => import('@/views/hazard/HazardAnalyze.vue'), meta: { title: 'AI 分析' } },
      { path: 'hazards/audit', name: 'HazardAudit', component: () => import('@/views/hazard/HazardAudit.vue'), meta: { title: '隐患处理', roles: [2, 3] } },
      { path: 'hazards/:id', name: 'HazardDetail', component: () => import('@/views/hazard/HazardDetail.vue'), meta: { title: '隐患详情', hidden: true } },

      // 模块二 AI 助手
      { path: 'ai/assistant', name: 'AiAssistant', component: () => import('@/views/ai/AiAssistant.vue'), meta: { title: 'AI 助手' } },

      // O10 法规文档库（全角色可浏览；管理端含上传/停用/删除）
      { path: 'documents', name: 'DocLibrary', component: () => import('@/views/document/DocLibrary.vue'), meta: { title: '法规文档库' } },

      // O8 用户端考试工坊
      { path: 'exam/workshop', name: 'ExamWorkshop', component: () => import('@/views/exam/ExamWorkshop.vue'), meta: { title: '考试工坊' } },

      // 模块三 考试工坊 · 管理（SAFETY/ADMIN）
      { path: 'exam/questions', name: 'QuestionBank', component: () => import('@/views/exam/QuestionBank.vue'), meta: { title: '题库管理', roles: [2, 3] } },
      { path: 'exam/ai/generate', name: 'AiGenerate', component: () => import('@/views/exam/ai/AiGenerate.vue'), meta: { title: 'AI 出题', roles: [2, 3] } },
      { path: 'exam/ai/batches', name: 'AiBatches', component: () => import('@/views/exam/ai/AiBatches.vue'), meta: { title: '批次审核', roles: [2, 3] } },
      { path: 'exam/ai/batches/:batchId', name: 'AiBatchDetail', component: () => import('@/views/exam/ai/AiBatchDetail.vue'), meta: { title: '批次详情', roles: [2, 3], hidden: true } },
      { path: 'exam/ai/stats', name: 'AiStats', component: () => import('@/views/exam/ai/AiStats.vue'), meta: { title: '出题统计', roles: [2, 3] } },
      { path: 'exam/papers', name: 'PaperList', component: () => import('@/views/exam/paper/PaperList.vue'), meta: { title: '试卷管理', roles: [2, 3] } },
      { path: 'exam/papers/create', name: 'PaperCreate', component: () => import('@/views/exam/paper/PaperCreate.vue'), meta: { title: '组卷', roles: [2, 3], hidden: true } },
      { path: 'exam/papers/:pid', name: 'PaperDetail', component: () => import('@/views/exam/paper/PaperDetail.vue'), meta: { title: '试卷详情', roles: [2, 3], hidden: true } },

      // 模块三 考试中心（任意登录用户）
      { path: 'exams', name: 'ExamPicker', component: () => import('@/views/exam/ExamPicker.vue'), meta: { title: '在线考试' } },
      { path: 'exams/records', name: 'ExamRecords', component: () => import('@/views/exam/ExamRecords.vue'), meta: { title: '考试记录' } },
      { path: 'exams/stats', name: 'ExamStats', component: () => import('@/views/exam/ExamStats.vue'), meta: { title: '考试统计' } },
      { path: 'exams/wrong-book', name: 'WrongBook', component: () => import('@/views/exam/WrongBook.vue'), meta: { title: '我的错题' } },
      { path: 'exams/:recordId', name: 'ExamTaking', component: () => import('@/views/exam/ExamTaking.vue'), meta: { title: '考试作答', hidden: true } },
      { path: 'exams/:recordId/result', name: 'ExamResult', component: () => import('@/views/exam/ExamResult.vue'), meta: { title: '成绩单', hidden: true } },

      // 个人中心（任意登录）
      { path: 'profile', name: 'Profile', component: () => import('@/views/profile/Profile.vue'), meta: { title: '个人中心' } },

      // 系统管理（仅 ADMIN）
      { path: 'admin/users', name: 'UserManage', component: () => import('@/views/admin/UserManage.vue'), meta: { title: '用户管理', roles: [3] } },
      { path: 'admin/logs', name: 'AuditLogs', component: () => import('@/views/admin/AuditLogs.vue'), meta: { title: '审计日志', roles: [3] } },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/NotFound.vue'),
    meta: { title: '页面不存在', hidden: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/** 全局前置守卫（FRONTEND.md §3.2） */
router.beforeEach(async (to) => {
  const userStore = useUserStore()
  document.title = to.meta.title ? `${to.meta.title} · 蜀道安全助手` : '蜀道安全助手'

  // 公开页（/login）
  if (to.meta.public) {
    if (userStore.isLoggedIn && to.path === '/login') return { path: '/home' }
    return true
  }

  // 未登录 → 登录页（带 redirect）
  if (!userStore.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 已登录但无 user（刷新场景）→ 拉 /me
  if (!userStore.user) {
    try {
      await userStore.fetchMe()
    } catch {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  // 角色门禁
  if (to.meta.roles && !to.meta.roles.includes(userStore.roleId)) {
    ElMessage.warning('无权访问该页面')
    return { path: '/home' }
  }

  return true
})

export default router
