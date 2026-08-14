<template>
  <div class="page-container">
    <el-card shadow="never" class="filter-card">
      <div class="filter-bar">
        <el-select v-model="query.gen_mode" placeholder="组卷方式" clearable style="width: 150px">
          <el-option v-for="m in PAPER_GEN_MODES" :key="m.value" :label="m.label" :value="m.value" />
        </el-select>
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 130px">
          <el-option v-for="s in PAPER_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-input
          v-model="query.keyword"
          placeholder="试卷名称关键词"
          clearable
          style="width: 200px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button type="primary" :icon="'Search'" @click="handleSearch">搜索</el-button>
        <el-button :icon="'Refresh'" @click="handleReset">重置</el-button>
        <div class="filter-spacer" />
        <el-dropdown @command="handleCreateMode">
          <el-button type="primary" :icon="'Plus'">
            新建试卷
            <el-icon><component :is="'ArrowDown'" /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="manual">手动组卷</el-dropdown-item>
              <el-dropdown-item command="auto">自动组卷</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="pageData?.items ?? []" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="试卷名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="total_score" label="总分" width="70" />
        <el-table-column prop="pass_score" label="及格线" width="80" />
        <el-table-column label="时长(分)" width="90">
          <template #default="{ row }">{{ (row as PaperListItem).duration }}</template>
        </el-table-column>
        <el-table-column prop="question_count" label="题数" width="70" />
        <el-table-column label="组卷方式" width="110">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ paperGenModeLabel((row as PaperListItem).gen_mode) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="paperStatusMeta((row as PaperListItem).status).tag">
              {{ paperStatusMeta((row as PaperListItem).status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="creator_name" label="创建人" width="100" />
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatDateTime((row as PaperListItem).create_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="goDetail((row as PaperListItem).id)">详情</el-button>
            <el-button link type="success" size="small" @click="handleToggleStatus(row as PaperListItem)">
              {{ (row as PaperListItem).status === 'PUBLISHED' ? '停用' : '发布' }}
            </el-button>
            <el-button link type="warning" size="small" @click="openEdit(row as PaperListItem)">编辑配置</el-button>
            <el-tooltip :disabled="(row as PaperListItem).status !== 'PUBLISHED'" content="已发布不可删除" placement="top">
              <el-button
                link
                type="danger"
                size="small"
                :disabled="(row as PaperListItem).status === 'PUBLISHED'"
                @click="handleDelete(row as PaperListItem)"
              >
                删除
              </el-button>
            </el-tooltip>
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

    <!-- 编辑配置 -->
    <el-dialog v-model="editVisible" title="编辑试卷配置" width="440px" :close-on-click-modal="false">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="88px">
        <el-form-item label="试卷名称" prop="name">
          <el-input v-model="editForm.name" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="考试时长" prop="duration">
          <el-select v-model="editForm.duration" style="width: 100%">
            <el-option v-for="d in PAPER_DURATIONS" :key="d.value" :label="d.label" :value="d.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="总分" prop="total_score">
          <el-input-number v-model="editForm.total_score" :min="10" :max="500" :disabled="editingIsPublished" />
          <span v-if="editingIsPublished" class="field-tip">已发布试卷总分锁定，不可修改</span>
        </el-form-item>
        <el-form-item label="及格线" prop="pass_score">
          <el-input-number v-model="editForm.pass_score" :min="1" :max="500" :disabled="editingIsPublished" />
          <span v-if="editingIsPublished" class="field-tip">已发布试卷及格线锁定，不可修改</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSubmitting" @click="confirmEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { PAPER_DURATIONS, PAPER_GEN_MODES, PAPER_STATUSES, paperGenModeLabel, paperStatusMeta } from '@/utils/constants'
import { deletePaper, listPapers, updatePaper, type PaperQuery } from '@/api/exam'
import { formatDateTime } from '@/utils/format'
import type { PageResult } from '@/types/api'
import type { PaperListItem, PaperStatus } from '@/types/models/exam'

const router = useRouter()
const loading = ref(false)
const pageData = ref<PageResult<PaperListItem> | null>(null)
const query = reactive<PaperQuery>({
  gen_mode: '',
  status: '',
  keyword: '',
  page: 1,
  page_size: 20,
})

const editVisible = ref(false)
const editingPaper = ref<PaperListItem | null>(null)
const editSubmitting = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive({ name: '', duration: 30 as 30 | 60 | 90, pass_score: 60, total_score: 100 })

const editingIsPublished = computed(() => editingPaper.value?.status === 'PUBLISHED')

const editRules = reactive<FormRules>({
  name: [{ required: true, message: '请输入试卷名称', trigger: 'blur' }],
  duration: [{ required: true, message: '请选择考试时长', trigger: 'change' }],
  total_score: [{ required: true, message: '请输入总分', trigger: 'blur' }],
  pass_score: [{ required: true, message: '请输入及格线', trigger: 'blur' }],
})

async function load(): Promise<void> {
  loading.value = true
  try {
    pageData.value = await listPapers({ ...query })
  } finally {
    loading.value = false
  }
}

function handleSearch(): void {
  query.page = 1
  void load()
}

function handleReset(): void {
  query.gen_mode = ''
  query.status = ''
  query.keyword = ''
  query.page = 1
  void load()
}

function handleSizeChange(): void {
  query.page = 1
  void load()
}

function handleCreateMode(mode: string): void {
  router.push({ path: '/exam/papers/create', query: { mode } })
}

function goDetail(pid: number): void {
  router.push(`/exam/papers/${pid}`)
}

function handleToggleStatus(p: PaperListItem): void {
  const target: PaperStatus = p.status === 'PUBLISHED' ? 'DISABLED' : 'PUBLISHED'
  const label = target === 'PUBLISHED' ? '发布' : '停用'
  ElMessageBox.confirm(`确定${label}试卷「${p.name}」吗？`, `${label}确认`, {
    type: 'warning',
  })
    .then(async () => {
      await updatePaper(p.id, { status: target })
      ElMessage.success(`${label}成功`)
      void load()
    })
    .catch(() => {
      /* 取消 */
    })
}

function openEdit(p: PaperListItem): void {
  editingPaper.value = p
  editForm.name = p.name
  editForm.duration = p.duration as 30 | 60 | 90
  editForm.pass_score = p.pass_score
  editForm.total_score = p.total_score
  editVisible.value = true
}

async function confirmEdit(): Promise<void> {
  const ok = await editFormRef.value?.validate().catch(() => false)
  if (!ok) return
  if (editForm.pass_score > editForm.total_score) {
    ElMessage.warning('及格线不能高于总分')
    return
  }
  if (!editingPaper.value) return
  editSubmitting.value = true
  try {
    await updatePaper(editingPaper.value.id, {
      name: editForm.name.trim(),
      duration: editForm.duration,
      pass_score: editingIsPublished.value ? undefined : editForm.pass_score,
      total_score: editingIsPublished.value ? undefined : editForm.total_score,
    })
    ElMessage.success('配置已更新')
    editVisible.value = false
    void load()
  } catch {
    // 后端 message 已提示（如已发布禁改、有进行中考试禁改时长）
  } finally {
    editSubmitting.value = false
  }
}

function handleDelete(p: PaperListItem): void {
  if (p.status === 'PUBLISHED') {
    ElMessage.warning('已发布试卷不可删除，请先停用')
    return
  }
  ElMessageBox.confirm(`确定删除试卷「${p.name}」吗？`, '删除确认', { type: 'warning' })
    .then(async () => {
      await deletePaper(p.id)
      ElMessage.success('删除成功')
      if (pageData.value && pageData.value.items.length === 1 && query.page && query.page > 1) {
        query.page -= 1
      }
      void load()
    })
    .catch(() => {
      /* 取消 */
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
.field-tip {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-color-danger);
}
</style>
