<template>
  <div class="page-container">
    <el-card shadow="never" class="filter-card">
      <div class="filter-bar">
        <el-select v-model="query.type" placeholder="题型" clearable style="width: 130px">
          <el-option v-for="t in QUESTION_TYPES" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
        <el-select v-model="query.difficulty" placeholder="难度" clearable style="width: 120px">
          <el-option v-for="d in DIFFICULTIES" :key="d.value" :label="d.label" :value="d.value" />
        </el-select>
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 130px">
          <el-option v-for="s in QUESTION_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select v-model="query.source" placeholder="来源" clearable style="width: 130px">
          <el-option v-for="s in SOURCE_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-input
          v-model="query.knowledge_point"
          placeholder="知识点"
          clearable
          style="width: 160px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="query.keyword"
          placeholder="题干关键词"
          clearable
          style="width: 180px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button type="primary" :icon="'Search'" @click="handleSearch">搜索</el-button>
        <el-button :icon="'Refresh'" @click="handleReset">重置</el-button>
        <div class="filter-spacer" />
        <el-button type="primary" :icon="'Plus'" @click="openCreate">新建题目</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="pageData?.items ?? []" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="题型" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ questionTypeLabel(row.type as QuestionType) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="content" label="题干" min-width="260" show-overflow-tooltip />
        <el-table-column prop="knowledge_point" label="知识点" min-width="140" show-overflow-tooltip />
        <el-table-column label="难度" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="difficultyMeta(row.difficulty as QuestionDifficulty).tag">
              {{ difficultyMeta(row.difficulty as QuestionDifficulty).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="90">
          <template #default="{ row }">
            {{ sourceLabel(row.source) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="questionStatusMeta(row.status as QuestionStatus).tag">
              {{ questionStatusMeta(row.status as QuestionStatus).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="溯源" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.source_law_title">{{ row.source_law_title }}<template v-if="row.source_article_no">·{{ row.source_article_no }}</template></span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row as Question)">编辑</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row as Question)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="pageData?.total ?? 0"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="load"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <QuestionFormDialog
      v-model="dialogVisible"
      :question="editingQuestion"
      @success="load"
    />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DIFFICULTIES, QUESTION_STATUSES, QUESTION_TYPES, difficultyMeta, questionStatusMeta, questionTypeLabel } from '@/utils/constants'
import { deleteQuestion, listQuestions, type QuestionQuery } from '@/api/exam'
import type { PageResult } from '@/types/api'
import type { Question, QuestionDifficulty, QuestionStatus, QuestionType } from '@/types/models/exam'
import QuestionFormDialog from '@/components/exam/QuestionFormDialog.vue'

const SOURCE_OPTIONS = [
  { value: 'manual', label: '人工录入' },
  { value: 'ai', label: '智能生成' },
] as const

function sourceLabel(v: string): string {
  return SOURCE_OPTIONS.find((s) => s.value === v)?.label ?? v
}

const loading = ref(false)
const pageData = ref<PageResult<Question> | null>(null)
const query = reactive<QuestionQuery>({
  type: '',
  difficulty: '',
  status: '',
  source: '',
  knowledge_point: '',
  keyword: '',
  page: 1,
  page_size: 20,
})

const dialogVisible = ref(false)
const editingQuestion = ref<Question | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    pageData.value = await listQuestions({ ...query })
  } finally {
    loading.value = false
  }
}

function handleSearch(): void {
  query.page = 1
  void load()
}

function handleReset(): void {
  query.type = ''
  query.difficulty = ''
  query.status = ''
  query.source = ''
  query.knowledge_point = ''
  query.keyword = ''
  query.page = 1
  void load()
}

function handleSizeChange(): void {
  query.page = 1
  void load()
}

function openCreate(): void {
  editingQuestion.value = null
  dialogVisible.value = true
}

function openEdit(q: Question): void {
  editingQuestion.value = q
  dialogVisible.value = true
}

function handleDelete(q: Question): void {
  ElMessageBox.confirm(`确定删除题目 #${q.id} 吗？`, '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
    .then(async () => {
      await deleteQuestion(q.id)
      ElMessage.success('删除成功')
      // 当前页只剩一行且非首页时回退一页
      if (pageData.value && pageData.value.items.length === 1 && query.page && query.page > 1) {
        query.page -= 1
      }
      void load()
    })
    .catch(() => {
      /* 取消删除 */
    })
}

void load()
</script>

<style scoped>
.filter-card {
  margin-bottom: 12px;
}
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.filter-spacer {
  flex: 1;
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
