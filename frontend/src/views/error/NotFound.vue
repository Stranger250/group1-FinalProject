<template>
  <div class="not-found">
    <h1>404</h1>
    <p>页面不存在或已被移除</p>
    <el-button type="primary" @click="router.push('/home')">返回首页</el-button>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<style scoped>
.not-found {
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--el-bg-color-page, #f6f5f1);
}
.not-found h1 {
  font-size: 72px;
  margin: 0;
  color: var(--el-color-primary, #1e5a52);
}
.not-found p {
  color: var(--el-text-color-secondary, #707a78);
  margin: 12px 0 24px;
}
</style>
