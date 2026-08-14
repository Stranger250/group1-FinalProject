import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** 页面标题（document.title） */
    title?: string
    /** 无需登录（如 /login） */
    public?: boolean
    /** 角色门禁（role_id 白名单），如 [2,3]；缺省=任意登录用户 */
    roles?: number[]
    /** 不在侧栏菜单显示（详情/作答等子页） */
    hidden?: boolean
  }
}
