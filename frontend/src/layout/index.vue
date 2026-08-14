<template>
  <el-container class="app-layout">
    <Sidebar />
    <el-container class="app-body">
      <HeaderBar />
      <el-main class="app-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import Sidebar from './Sidebar.vue'
import HeaderBar from './HeaderBar.vue'
</script>

<style scoped>
.app-layout {
  height: 100vh;
}
.app-body {
  flex-direction: column;
}
.app-content {
  padding: 16px;
  overflow-y: auto;
  background-color: var(--el-bg-color-page, #f6f5f1);
}
</style>
