<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '@/utils/markdown'

const props = withDefaults(
  defineProps<{
    /** AI/法规正文（markdown） */
    text?: string
    /** 流式生成中：显示打字光标动画 */
    loading?: boolean
  }>(),
  { text: '', loading: false },
)

/**
 * 净化 markdown → 安全 HTML；再把 [n] 引用脚注渲染为上标（与引用条序号对应）。
 * renderMarkdown 已过 DOMPurify 白名单消毒，此处仅追加受控 sup 标签，数字已限定 \d。
 */
const html = computed(() => {
  const sanitized = renderMarkdown(props.text)
  return sanitized.replace(/\[(\d{1,3})\]/g, '<sup class="cite-ref">$1</sup>')
})
</script>

<template>
  <div class="markdown-body">
    <div class="md-content" v-html="html" />
    <span v-if="loading" class="typing-cursor" aria-label="正在生成" />
  </div>
</template>

<style scoped>
.markdown-body {
  line-height: 1.7;
  word-break: break-word;
}
.md-content :deep(p) {
  margin: 0.4em 0;
}
.md-content :deep(h1),
.md-content :deep(h2),
.md-content :deep(h3),
.md-content :deep(h4) {
  margin: 0.8em 0 0.4em;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.md-content :deep(ul),
.md-content :deep(ol) {
  margin: 0.4em 0;
  padding-left: 1.5em;
}
.md-content :deep(li) {
  margin: 0.2em 0;
}
.md-content :deep(code) {
  background-color: var(--el-fill-color, #f0eee7);
  border-radius: 3px;
  padding: 1px 4px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 0.92em;
  color: var(--el-text-color-regular, #4b5553);
}
.md-content :deep(pre) {
  background-color: var(--el-fill-color-light, #f4f2eb);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px 12px;
  overflow-x: auto;
}
.md-content :deep(pre code) {
  background-color: transparent;
  padding: 0;
}
.md-content :deep(blockquote) {
  margin: 0.5em 0;
  padding: 4px 12px;
  border-left: 3px solid var(--el-color-primary);
  background-color: var(--brand-soft, #e6efed);
  color: var(--el-text-color-regular);
}
.md-content :deep(table) {
  border-collapse: collapse;
  margin: 0.6em 0;
  width: 100%;
}
.md-content :deep(th),
.md-content :deep(td) {
  border: 1px solid var(--el-border-color-light);
  padding: 6px 10px;
}
.md-content :deep(a) {
  color: var(--el-color-primary);
}
.md-content :deep(img) {
  max-width: 100%;
}
/* 引用脚注上标 */
.md-content :deep(.cite-ref) {
  color: var(--el-color-primary);
  font-size: 0.75em;
  font-weight: 600;
  margin: 0 1px;
  cursor: default;
}
/* 打字光标 */
.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -0.15em;
  background-color: var(--el-color-primary);
  animation: cursor-blink 1s steps(2, start) infinite;
}
@keyframes cursor-blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}
</style>
