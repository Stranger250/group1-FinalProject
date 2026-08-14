<template>
  <div class="page-container">
    <el-card v-loading="loading" shadow="never" class="info-card">
      <div class="head-row">
        <div class="head-left">
          <el-button link :icon="'ArrowLeft'" @click="router.push('/exam/papers')">返回列表</el-button>
          <span class="paper-name">{{ detail?.name ?? '加载中…' }}</span>
          <el-tag v-if="detail" size="small" :type="paperStatusMeta(detail.status).tag">
            {{ paperStatusMeta(detail.status).label }}
          </el-tag>
        </div>
        <div class="head-ops" v-if="detail">
          <el-button type="success" size="small" :icon="'Upload'" @click="handleToggleStatus">
            {{ detail.status === 'PUBLISHED' ? '停用' : '发布' }}
          </el-button>
          <el-button type="primary" size="small" :icon="'Setting'" @click="openEdit">编辑配置</el-button>
          <el-tooltip :disabled="detail.status !== 'PUBLISHED'" content="已发布不可删除" placement="top">
            <el-button type="danger" size="small" :icon="'Delete'" :disabled="detail.status === 'PUBLISHED'" @click="handleDelete">
              删除
            </el-button>
          </el-tooltip>
        </div>
      </div>

      <el-descriptions v-if="detail" :column="4" border size="small">
        <el-descriptions-item label="试卷名称">{{ detail.name }}</el-descriptions-item>
        <el-descriptions-item label="组卷方式">{{ paperGenModeLabel(detail.gen_mode) }}</el-descriptions-item>
        <el-descriptions-item label="总分">{{ detail.total_score }}</el-descriptions-item>
        <el-descriptions-item label="及格线">{{ detail.pass_score }}</el-descriptions-item>
        <el-descriptions-item label="考试时长">{{ detail.duration }} 分钟</el-descriptions-item>
        <el-descriptions-item label="题目数量">{{ detail.question_count }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ detail.creator_name ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDateTime(detail.create_time) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-title">
          题目预览
          <span class="card-sub">共 {{ detail?.questions?.length ?? 0 }} 题（含答案与解析，管理端可见）</span>
        </div>
      </template>
      <div v-for="item in detail?.questions ?? []" :key="item.seq" class="paper-q">
        <template v-if="item.question">
          <QuestionCard :question="toQuestion(item.question)" :seq="item.seq" :score="item.score" paper-preview />
        </template>
        <el-alert v-else :title="`第 ${item.seq} 题：题目已失效（已被删除或停用）`" type="warning" :closable="false" show-icon class="paper-q-missing" />
      </div>
      <el-empty v-if="!loading && !detail?.questions?.length" description="该试卷暂无题目" />
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
          <el-input-number v-model="editForm.total_score" :min="10" :max="500" :disabled="isPublished" />
          <span v-if="isPublished" class="field-tip">已发布试卷总分锁定，不可修改</span>
        </el-form-item>
        <el-form-item label="及格线" prop="pass_score">
          <el-input-number v-model="editForm.pass_score" :min="1" :max="500" :disabled="isPublished" />
          <span v-if="isPublished" class="field-tip">已发布试卷及格线锁定，不可修改</span>
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
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { PAPER_DURATIONS, paperGenModeLabel, paperStatusMeta } from '@/utils/constants'
import { deletePaper, getPaper, updatePaper } from '@/api/exam'
import { formatDateTime } from '@/utils/format'
import type { PaperDetail, PaperQuestionPreview, Question } from '@/types/models/exam'
import QuestionCard from '@/components/exam/QuestionCard.vue'

const route = useRoute()
const router = useRouter()

const pid = computed(() => Number(route.params.pid))
const loading = ref(false)
const detail = ref<PaperDetail | null>(null)

const isPublished = computed(() => detail.value?.status === 'PUBLISHED')

const editVisible = ref(false)
const editSubmitting = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive({ name: '', duration: 60 as 30 | 60 | 90, pass_score: 60, total_score: 100 })

const editRules = reactive<FormRules>({
  name: [{ required: true, message: '请输入试卷名称', trigger: 'blur' }],
  duration: [{ required: true, message: '请选择考试时长', trigger: 'change' }],
  total_score: [{ required: true, message: '请输入总分', trigger: 'blur' }],
  pass_score: [{ required: true, message: '请输入及格线', trigger: 'blur' }],
})

async function load(): Promise<void> {
  if (!pid.value) return
  loading.value = true
  try {
    detail.value = await getPaper(pid.value)
  } catch {
    // 404 message 已全局提示，退回列表
    router.push('/exam/papers')
  } finally {
    loading.value = false
  }
}

function toQuestion(p: PaperQuestionPreview): Question {
  return {
    id: p.id,
    batch_id: null,
    type: p.type,
    content: p.content,
    options: p.options,
    answer: p.answer,
    analysis: p.analysis,
    knowledge_point: p.knowledge_point,
    difficulty: p.difficulty,
    source: 'manual',
    sources: null,
    source_law_title: p.source_law_title,
    source_article_no: p.source_article_no,
    status: 'APPROVED',
    reviewer: null,
    review_note: null,
    interference_verified: 0,
    rewrite_of: null,
    rewrite_feedback: null,
    create_time: null,
    update_time: null,
  }
}

function handleToggleStatus(): void {
  if (!detail.value) return
  const target = detail.value.status === 'PUBLISHED' ? 'DISABLED' : 'PUBLISHED'
  const label = target === 'PUBLISHED' ? '发布' : '停用'
  ElMessageBox.confirm(`确定${label}试卷「${detail.value.name}」吗？`, `${label}确认`, {
    type: 'warning',
  })
    .then(async () => {
      await updatePaper(detail.value!.id, { status: target })
      ElMessage.success(`${label}成功`)
      await load()
    })
    .catch(() => {
      /* 取消 */
    })
}

function openEdit(): void {
  if (!detail.value) return
  editForm.name = detail.value.name
  editForm.duration = detail.value.duration as 30 | 60 | 90
  editForm.pass_score = detail.value.pass_score
  editForm.total_score = detail.value.total_score
  editVisible.value = true
}

async function confirmEdit(): Promise<void> {
  const ok = await editFormRef.value?.validate().catch(() => false)
  if (!ok) return
  if (!detail.value) return
  if (editForm.pass_score > editForm.total_score) {
    ElMessage.warning('及格线不能高于总分')
    return
  }
  editSubmitting.value = true
  try {
    await updatePaper(detail.value.id, {
      name: editForm.name.trim(),
      duration: editForm.duration,
      pass_score: isPublished.value ? undefined : editForm.pass_score,
      total_score: isPublished.value ? undefined : editForm.total_score,
    })
    ElMessage.success('配置已更新')
    editVisible.value = false
    await load()
  } catch {
    // 后端 message 已提示
  } finally {
    editSubmitting.value = false
  }
}

function handleDelete(): void {
  if (!detail.value) return
  if (detail.value.status === 'PUBLISHED') {
    ElMessage.warning('已发布试卷不可删除，请先停用')
    return
  }
  ElMessageBox.confirm(`确定删除试卷「${detail.value.name}」吗？`, '删除确认', { type: 'warning' })
    .then(async () => {
      await deletePaper(detail.value!.id)
      ElMessage.success('删除成功')
      router.push('/exam/papers')
    })
    .catch(() => {
      /* 取消 */
    })
}

void load()
</script>

<style scoped>
.info-card {
  margin-bottom: 12px;
}
.head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.head-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.paper-name {
  font-size: 16px;
  font-weight: 600;
}
.head-ops {
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
}
.card-sub {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.paper-q {
  margin-bottom: 12px;
}
.paper-q-missing {
  margin-bottom: 12px;
}
.field-tip {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-color-danger);
}
</style>
