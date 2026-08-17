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
        <el-button :icon="'Upload'" @click="openImport">导入</el-button>
        <el-button :icon="'Download'" @click="doExport">导出</el-button>
        <el-button text @click="doDownloadTemplate">模板</el-button>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">新建题目</el-button>
      </div>
    </el-card>

    <!-- 导入对话框 -->
    <el-dialog v-model="importVisible" title="批量导入题目（xlsx）" width="560px" :close-on-click-modal="false">
      <el-alert type="info" :closable="false" class="import-tip">
        表头：type / content / options（多选项用 | 分隔）/ answer / analysis / knowledge_point / difficulty。
        可先下载<el-link type="primary" @click="doDownloadTemplate">导入模板</el-link>参考格式。
      </el-alert>
      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        accept=".xlsx,.xlsm"
        :on-change="onImportFileChange"
        :on-remove="() => (importFile = null)"
        style="margin-top: 12px"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽 .xlsx 文件到此处，或<em>点击选择</em></div>
      </el-upload>
      <div v-if="importResult" class="import-result">
        <el-alert
          v-if="importResult.imported > 0"
          type="success"
          :closable="false"
          :title="`成功导入 ${importResult.imported} 道题`"
        />
        <el-alert v-if="importResult.errors?.length" type="warning" :closable="false"
                  :title="`${importResult.errors.length} 行校验失败`">
          <div v-for="e in importResult.errors.slice(0, 8)" :key="e.row" class="import-err">
            第 {{ e.row }} 行：{{ e.error }}
          </div>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="importVisible = false">关闭</el-button>
        <el-button type="primary" :loading="importing" :disabled="!importFile" @click="doImport">开始导入</el-button>
      </template>
    </el-dialog>

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
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <!-- O8：普通用户提交的题目（PENDING）由管理员审核 -->
            <template v-if="(row.status as QuestionStatus) === 'PENDING'">
              <el-button link type="success" size="small" @click="handleReview(row as Question, 'APPROVE')">通过</el-button>
              <el-button link type="danger" size="small" @click="handleReview(row as Question, 'REJECT')">驳回</el-button>
            </template>
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
import { ElMessage, ElMessageBox, type UploadFile } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { DIFFICULTIES, QUESTION_STATUSES, QUESTION_TYPES, difficultyMeta, questionStatusMeta, questionTypeLabel } from '@/utils/constants'
import { deleteQuestion, exportQuestionsUrl, exportTemplateUrl, importQuestions, listQuestions, reviewUserQuestion, type QuestionQuery } from '@/api/exam'
import type { PageResult } from '@/types/api'
import type { Question, QuestionDifficulty, QuestionStatus, QuestionType } from '@/types/models/exam'
import QuestionFormDialog from '@/components/exam/QuestionFormDialog.vue'

// ---------- Excel 导入/导出 ----------
const importVisible = ref(false)
const importing = ref(false)
const importFile = ref<File | null>(null)
const importResult = ref<{ imported: number; errors: { row: number; error: string }[] } | null>(null)

function openImport(): void {
  importVisible.value = true
  importFile.value = null
  importResult.value = null
}

function onImportFileChange(file: UploadFile): void {
  importFile.value = (file.raw as File) ?? null
}

function doDownloadTemplate(): void {
  window.open(exportTemplateUrl(), '_blank')
}

function doExport(): void {
  window.open(exportQuestionsUrl(), '_blank')
}

async function doImport(): Promise<void> {
  if (!importFile.value) {
    ElMessage.warning('请先选择 .xlsx 文件')
    return
  }
  importing.value = true
  importResult.value = null
  try {
    const res = await importQuestions(importFile.value)
    if (res.code === 200) {
      importResult.value = res.data
      if (res.data.imported > 0) {
        ElMessage.success(`成功导入 ${res.data.imported} 道题`)
        void load()
      }
    } else {
      ElMessage.error(res.message || '导入失败')
    }
  } catch {
    /* 全局提示 */
  } finally {
    importing.value = false
  }
}

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

/** O8 审核用户提交的题目：通过 APPROVED / 驳回 REJECTED（驳回需填意见） */
function handleReview(q: Question, action: 'APPROVE' | 'REJECT'): void {
  if (action === 'REJECT') {
    ElMessageBox.prompt('请填写驳回意见（提交人可见）', '驳回题目', {
      type: 'warning',
      inputType: 'textarea',
      inputValidator: (v: string) => (v && v.trim() ? true : '驳回必须填写意见'),
    })
      .then(async ({ value }) => {
        await reviewUserQuestion(q.id, { action, review_note: value.trim() })
        ElMessage.success('已驳回')
        void load()
      })
      .catch(() => {})
    return
  }
  ElMessageBox.confirm(`确认通过题目 #${q.id} 吗？通过后进入题库供组卷。`, '审核通过', { type: 'info' })
    .then(async () => {
      await reviewUserQuestion(q.id, { action })
      ElMessage.success('已通过')
      void load()
    })
    .catch(() => {})
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
