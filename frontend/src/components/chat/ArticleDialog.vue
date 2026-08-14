<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getArticle } from '@/api/ai'
import type { ArticleDetail } from '@/types/models/chat'
import { renderMarkdown } from '@/utils/markdown'
import { formatDate } from '@/utils/format'

const props = defineProps<{
  modelValue: boolean
  docId: string
  articleNo: string
}>()

const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const loading = ref(false)
const article = ref<ArticleDetail | null>(null)
const error = ref('')

/** 打开或切换引用时拉取原文 */
watch(
  () => [props.modelValue, props.docId, props.articleNo],
  ([visible]) => {
    if (visible) void load()
  },
)

async function load() {
  if (!props.docId || !props.articleNo) return
  loading.value = true
  error.value = ''
  article.value = null
  try {
    article.value = await getArticle(props.docId, props.articleNo)
  } catch {
    error.value = '未找到对应条文，可能已被下架或删除'
  } finally {
    loading.value = false
  }
}

function close() {
  emit('update:modelValue', false)
}

/** 条文正文（可能含条例层级文本），经净化后渲染 */
const contentHtml = computed(() => renderMarkdown(article.value?.content ?? ''))

/** 条号展示：article_no 已含「第…条」则原样，否则补壳（避免「第第十六条条」） */
const articleNoDisplay = computed(() => {
  const n = (article.value?.article_no ?? '').trim()
  if (!n) return ''
  return /^第.+条$/.test(n) ? n : `第 ${n} 条`
})
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="article?.title || '查看原文'"
    width="760px"
    class="article-dialog"
    :close-on-click-modal="true"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="article-body">
      <el-empty v-if="!loading && error" :description="error" />
      <template v-else-if="article">
        <div class="article-meta">
          <el-tag v-if="article.article_no" size="small" type="primary">{{ articleNoDisplay }}</el-tag>
          <el-tag v-if="article.doc_no" size="small">{{ article.doc_no }}</el-tag>
          <el-tag v-if="article.category" size="small" type="success">{{ article.category }}</el-tag>
          <el-tag v-if="article.effective_date" size="small" type="info">
            施行 {{ formatDate(article.effective_date) }}
          </el-tag>
        </div>
        <div class="article-content" v-html="contentHtml" />
        <div v-if="article.source_url" class="article-source">
          <a :href="article.source_url" target="_blank" rel="noopener noreferrer">查看原始出处</a>
        </div>
      </template>
    </div>
    <template #footer>
      <el-button @click="close">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.article-body {
  min-height: 200px;
  max-height: 62vh;
  overflow-y: auto;
}
.article-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.article-content {
  font-size: 14px;
  line-height: 2;
  color: var(--el-text-color-primary);
  word-break: break-word;
}
.article-source {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-extra-light, #f2efe8);
  font-size: 13px;
}
</style>
