import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import { setUnauthorizedHandler } from './api/request'
import { useUserStore } from './store/user'
import './style.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// 全量注册图标组件（实训项目简化配置，不做按需）
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 401 统一登出跳登录（注册处理器，避免 request.ts 与 store 循环依赖）
setUnauthorizedHandler(() => {
  const userStore = useUserStore()
  userStore.logout()
  const redirect = router.currentRoute.value.fullPath
  router.push({ path: '/login', query: redirect && redirect !== '/login' ? { redirect } : {} })
})

app.mount('#app')
