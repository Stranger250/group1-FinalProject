<script setup lang="ts">
import type { ChatCitation } from '@/store/modules/chat'

defineProps<{ citations: ChatCitation[] }>()

const emit = defineEmits<{ (e: 'view', citation: ChatCitation): void }>()
</script>

<template>
  <div v-if="citations.length" class="citation-panel">
    <div class="citation-title">依据来源（{{ citations.length }}）</div>
    <div class="citation-list">
      <div
        v-for="(c, i) in citations"
        :key="i"
        class="citation-card"
        :class="{ disabled: !c.clickable }"
        :title="c.clickable ? '点击查看原文' : '该引用缺少条文定位，暂不支持查看原文'"
        @click="c.clickable && emit('view', c)"
      >
        <span v-if="c.n != null" class="cite-badge">{{ c.n }}</span>
        <div class="cite-body">
          <div class="cite-name">{{ c.name }}</div>
          <div v-if="c.chapter" class="cite-chapter">{{ c.chapter }}</div>
          <div v-if="c.content" class="cite-content">{{ c.content }}</div>
          <div v-if="c.score != null" class="cite-score">
            <span class="score-label">相关度</span>
            <el-progress
              class="score-bar"
              :percentage="Math.min(100, Math.max(0, Math.round(c.score * 100)))"
              :stroke-width="6"
              :show-text="false"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.citation-panel {
  margin-top: 10px;
}
.citation-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.citation-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.citation-card {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 10px;
  background-color: var(--el-bg-color-page, #f6f5f1);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s;
}
.citation-card:hover {
  border-color: var(--el-color-primary-light-5, #7aa19a);
  background-color: var(--brand-soft, #e6efed);
}
.citation-card.disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.citation-card.disabled:hover {
  border-color: var(--el-border-color-lighter);
  background-color: var(--el-bg-color-page, #f6f5f1);
}
.cite-badge {
  flex-shrink: 0;
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-primary);
  background-color: var(--brand-soft);
  border-radius: 4px;
  margin-top: 2px;
}
.cite-body {
  min-width: 0;
  flex: 1;
}
.cite-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.cite-chapter {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.cite-content {
  font-size: 12px;
  color: var(--el-text-color-regular);
  margin-top: 4px;
  line-height: 1.6;
  /* 不再截断到两行：卡片展示条文摘要全文（后端 snippet 已截到 400 字），点卡片看完整原文 */
  white-space: pre-wrap;
  word-break: break-word;
}
.cite-score {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.score-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.score-bar {
  flex: 1;
  min-width: 0;
}
</style>
