<template>
  <div class="page-container">
    <el-card shadow="never" class="filter-card">
      <div class="toolbar">
        <h3 class="block-title">我的错题</h3>
        <span class="sub-tip">共 {{ pageData?.total ?? 0 }} 道错题，按最近出错时间倒序</span>
      </div>
    </el-card>

    <div v-loading="loading">
      <el-empty v-if="!loading && !pageData?.items?.length" description="太棒了，暂无错题！" />
      <el-card v-for="w in pageData?.items ?? []" :key="w.question_id" shadow="never" class="wrong-card">
        <div class="w-head">
          <el-tag size="small" effect="plain">{{ questionTypeLabel(w.type) }}</el-tag>
          <span class="w-kp">{{ w.knowledge_point }}</span>
        </div>
        <div class="w-content markdown-body" v-html="renderMarkdown(w.content)" />
        <div class="w-answers">
          <span class="answer-item">
            我的作答：
            <b class="text-bad">{{ w.user_answer || '未作答' }}</b>
          </span>
          <span class="answer-item">
            正确答案：
            <b class="text-ok">{{ w.correct_answer }}</b>
          </span>
        </div>
        <div v-if="w.analysis" class="w-analysis">
          <span class="w-label">解析：</span>
          <span class="markdown-body" v-html="renderMarkdown(w.analysis)" />
        </div>
      </el-card>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="pageData?.total ?? 0"
          layout="total, prev, pager, next, sizes"
          :page-sizes="[10, 20, 50]"
          @change="load"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { getWrongBook } from '@/api/exam'
import type { PageResult } from '@/types/api'
import type { WrongBookItem } from '@/types/models/exam'
import { questionTypeLabel } from '@/utils/constants'
import { renderMarkdown } from '@/utils/markdown'

const loading = ref(false)
const pageData = ref<PageResult<WrongBookItem> | null>(null)
const query = reactive({ page: 1, page_size: 20 })

async function load(): Promise<void> {
  loading.value = true
  try {
    pageData.value = await getWrongBook(query.page, query.page_size)
  } catch {
    /* 全局提示 */
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.block-title {
  margin: 0;
  font-size: 15px;
}
.sub-tip {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.wrong-card {
  margin-bottom: 12px;
}
.w-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.w-kp {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.w-content {
  font-size: 15px;
  line-height: 1.7;
  margin-bottom: 8px;
}
.w-answers {
  display: flex;
  gap: 24px;
  padding: 8px 10px;
  background: #f8f9fb;
  border-radius: 6px;
  font-size: 13px;
}
.answer-item {
  display: flex;
  gap: 4px;
}
.text-ok {
  color: var(--el-color-success);
}
.text-bad {
  color: var(--el-color-danger);
}
.w-analysis {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.w-label {
  color: var(--el-text-color-secondary);
}
.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
