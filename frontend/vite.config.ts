import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 后端代理目标可用环境变量覆盖（默认 8000；多实例/CI 场景指向其他端口）
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_TARGET || 'http://127.0.0.1:8000'
  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      // 开发代理：/api 与 /uploads 全部转发到后端（FRONTEND.md §1；目标可用 VITE_API_TARGET 覆盖）
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true },
        '/uploads': { target: apiTarget, changeOrigin: true },
      },
    },
    build: {
      chunkSizeWarningLimit: 1500,
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes('node_modules/element-plus') || id.includes('@element-plus/icons-vue')) return 'element'
            if (
              id.includes('node_modules/vue') ||
              id.includes('vue-router') ||
              id.includes('pinia') ||
              id.includes('axios')
            ) {
              return 'vendor'
            }
          },
        },
      },
    },
  }
})
