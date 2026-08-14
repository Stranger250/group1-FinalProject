import { ROLE } from '@/types/models/user'

/** 侧栏菜单配置（FRONTEND.md §3）：按 meta.roles 过滤展示。 */
export interface MenuChild {
  title: string
  path: string
  icon?: string
  roles?: number[]
}

export interface MenuGroup {
  title: string
  icon?: string
  children: MenuChild[]
}

const MENU: MenuGroup[] = [
  {
    title: '首页',
    children: [
      { title: '首页', path: '/home', icon: 'HomeFilled' },
      { title: '个人中心', path: '/profile', icon: 'User' },
    ],
  },
  {
    title: '隐患管理',
    icon: 'Warning',
    children: [
      { title: '隐患列表', path: '/hazards', icon: 'List' },
      { title: '隐患上报', path: '/hazards/report', icon: 'EditPen' },
      { title: 'AI 分析', path: '/hazards/analyze', icon: 'MagicStick' },
    ],
  },
  {
    title: 'AI 助手',
    icon: 'ChatDotRound',
    children: [{ title: '智能问答', path: '/ai/assistant', icon: 'MagicStick' }],
  },
  {
    title: '考试工坊 · 管理',
    icon: 'DocumentChecked',
    children: [
      { title: '题库管理', path: '/exam/questions', icon: 'Collection', roles: [ROLE.SAFETY, ROLE.ADMIN] },
      { title: 'AI 出题', path: '/exam/ai/generate', icon: 'MagicStick', roles: [ROLE.SAFETY, ROLE.ADMIN] },
      { title: '批次审核', path: '/exam/ai/batches', icon: 'Stamp', roles: [ROLE.SAFETY, ROLE.ADMIN] },
      { title: '出题统计', path: '/exam/ai/stats', icon: 'TrendCharts', roles: [ROLE.SAFETY, ROLE.ADMIN] },
      { title: '试卷管理', path: '/exam/papers', icon: 'Tickets', roles: [ROLE.SAFETY, ROLE.ADMIN] },
    ],
  },
  {
    title: '考试中心',
    icon: 'Edit',
    children: [
      { title: '在线考试', path: '/exams', icon: 'Paperclip' },
      { title: '我的记录', path: '/exams/records', icon: 'DataLine' },
    ],
  },
  {
    title: '系统管理',
    icon: 'Setting',
    children: [
      { title: '用户管理', path: '/admin/users', icon: 'UserFilled', roles: [ROLE.ADMIN] },
    ],
  },
]

/** 按当前角色过滤菜单（meta.roles 缺省=全部可见） */
export function buildMenu(roleId: number): MenuGroup[] {
  return MENU.map((g) => ({
    ...g,
    children: g.children.filter((c) => !c.roles || c.roles.includes(roleId)),
  })).filter((g) => g.children.length > 0)
}
