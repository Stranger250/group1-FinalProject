<template>
  <div class="page-container">
    <el-card v-loading="loading" shadow="never" class="batch-head">
      <div class="head-row">
        <div class="head-left">
          <el-button link :icon="'ArrowLeft'" @click="router.push('/exam/ai/batches')">返回列表</el-button>
          <span class="batch-id">批次：{{ batchId }}</span>
        </div>
        <el-tag size="small" effect="plain">共 {{ detail?.total ?? 0 }} 题</el-tag>
      </div>
      <el-descriptions v-if="detail" :column="5" size="small" class="batch-stats">
        <el-descriptions-item label="总题数">{{ detail.total }}</el-descriptions-item>
        <el-descriptions-item label="待审核">
          <span class="stat-pending">{{ detail.pending }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="已通过">
          <span class="stat-approved">{{ detail.approved }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="已驳回">
          <span class="stat-rejected">{{ detail.rejected }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="通过率">
          <el-progress
            :percentage="passPercent"
            :status="passStatus"
            :stroke-width="12"
            style="width: 160px"
          />
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card v-if="pendingQuestions.length" shadow="never" class="batch-bar">
      <div class="batch-bar-inner">
        <el-checkbox v-model="allPendingSelected">全选待审</el-checkbox>
        <el-checkbox v-model="batchVerified">已核对干扰项（应用到批量操作）</el-checkbox>
        <div class="bar-spacer" />
        <el-button type="success" size="small" :icon="'CircleCheck'" :loading="batchSubmitting" @click="handleBatchApprove">
          批量通过<template v-if="selected.size">（{{ selected.size }}）</template>
        </el-button>
        <el-button type="danger" size="small" :icon="'CircleClose'" :loading="batchSubmitting" @click="openBatchReject">
          批量驳回<template v-if="selected.size">（{{ selected.size }}）</template>
        </el-button>
        <el-button v-if="selected.size" link size="small" @click="clearSelection">清空选择</el-button>
      </div>
    </el-card>

    <div class="question-list">
      <div v-for="(q, i) in detail?.questions ?? []" :key="q.id">
        <QuestionCard
          :question="q"
          :selectable="q.status === 'PENDING'"
          :checked="selected.has(q.id)"
          @update:checked="(v: boolean) => toggleSelected(q.id, v)"
          :seq="i + 1"
        >
          <template #actions>
            <el-button plain type="primary" size="small" @click="openReview(q)">审核</el-button>
            <el-button
              v-if="q.status === 'REJECTED'"
              plain
              type="warning"
              size="small"
              @click="openRewrite(q)"
            >
              AI 重写
            </el-button>
          </template>
        </QuestionCard>
      </div>
      <el-empty v-if="!loading && !detail?.questions.length" description="该批次暂无题目" />
    </div>

    <!-- 单题审核 -->
    <el-dialog v-model="reviewVisible" title="题目审核" width="480px" :close-on-click-modal="false">
      <div v-if="reviewQ" class="review-q-preview">
        <el-tag size="small" effect="plain">第 {{ reviewSeq }} 题</el-tag>
        <el-tag size="small" effect="plain">{{ questionTypeLabel(reviewQ.type) }}</el-tag>
        <el-tag size="small" :type="difficultyMeta(reviewQ.difficulty).tag" effect="plain">
          {{ difficultyMeta(reviewQ.difficulty).label }}
        </el-tag>
        <div class="review-q-content">{{ reviewQ.content }}</div>
      </div>
      <el-form label-width="92px">
        <el-form-item label="审核结果">
          <el-radio-group v-model="reviewAction">
            <el-radio value="APPROVE">通过</el-radio>
            <el-radio value="REJECT">驳回</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="reviewAction === 'REJECT'" label="审核意见" required>
          <el-input
            v-model="reviewNote"
            type="textarea"
            :rows="3"
            maxlength="255"
            show-word-limit
            placeholder="驳回必须填写审核意见"
          />
        </el-form-item>
        <el-form-item label="干扰项核对">
          <el-checkbox v-model="reviewVerified">已核对干扰项</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button type="primary" :loading="reviewSubmitting" @click="confirmReview">确认审核</el-button>
      </template>
    </el-dialog>

    <!-- AI 重写 -->
    <el-dialog v-model="rewriteVisible" title="AI 重写题目" width="480px" :close-on-click-modal="false">
      <div v-if="rewriteQ" class="review-q-preview">
        <div class="rewrite-origin">
          原题：第 {{ rewriteSeq }} 题
          <el-tag size="small" effect="plain" class="ml4">编号 #{{ rewriteQ.id }}</el-tag>
          <el-tag v-if="rewriteQ.review_note" size="small" type="danger" effect="plain" class="ml4">
            驳回意见：{{ rewriteQ.review_note }}
          </el-tag>
        </div>
        <div class="review-q-content">{{ rewriteQ.content }}</div>
      </div>
      <el-form label-width="92px">
        <el-form-item label="修订要求" required>
          <el-input
            v-model="rewriteFeedback"
            type="textarea"
            :rows="4"
            maxlength="255"
            show-word-limit
            placeholder="请描述需要修订的地方，如：把选项 B 改为与条款一致"
          />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="rewriteError"
        :title="rewriteError"
        type="error"
        :closable="false"
        show-icon
        class="rewrite-error"
      />
      <p class="rewrite-hint">
        AI 生成通常需要 1~3 分钟，请耐心等待；成功后本条题目会在原位就地更新，并回到「待审核」供复核。
      </p>
      <template #footer>
        <el-button @click="rewriteVisible = false">取消</el-button>
        <el-button type="primary" :loading="rewriteSubmitting" @click="confirmRewrite">开始重写</el-button>
      </template>
    </el-dialog>

    <!-- 批量驳回 -->
    <el-dialog v-model="batchRejectVisible" title="批量驳回" width="460px" :close-on-click-modal="false">
      <el-form label-width="92px">
        <el-form-item label="审核意见" required>
          <el-input
            v-model="batchRejectNote"
            type="textarea"
            :rows="3"
            maxlength="255"
            show-word-limit
            placeholder="整批驳回必须填写审核意见"
          />
        </el-form-item>
        <el-form-item label="干扰项核对">
          <el-checkbox v-model="batchRejectVerified">已核对干扰项</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchRejectVisible = false">取消</el-button>
        <el-button type="danger" :loading="batchSubmitting" @click="confirmBatchReject">确认驳回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError } from '@/api/request'
import { difficultyMeta, questionTypeLabel } from '@/utils/constants'
import { getBatchDetail, reviewBatch, reviewQuestion, rewriteQuestion } from '@/api/exam'
import type { BatchDetail, Question } from '@/types/models/exam'
import QuestionCard from '@/components/exam/QuestionCard.vue'

const route = useRoute()
const router = useRouter()

const batchId = computed(() => (route.params.batchId as string) ?? '')
const loading = ref(false)
const detail = ref<BatchDetail | null>(null)

// 批量选择（仅待审题可勾选）
const selected = ref<Set<number>>(new Set())
const batchVerified = ref(false)
const batchSubmitting = ref(false)

// 单题审核
const reviewVisible = ref(false)
const reviewQ = ref<Question | null>(null)
const reviewAction = ref<'APPROVE' | 'REJECT'>('APPROVE')
const reviewNote = ref('')
const reviewVerified = ref(false)
const reviewSubmitting = ref(false)

// AI 重写
const rewriteVisible = ref(false)
const rewriteQ = ref<Question | null>(null)
const rewriteFeedback = ref('')
const rewriteSubmitting = ref(false)
const rewriteError = ref('')

// 批量驳回
const batchRejectVisible = ref(false)
const batchRejectNote = ref('')
const batchRejectVerified = ref(false)

const pendingQuestions = computed<Question[]>(() =>
  (detail.value?.questions ?? []).filter((q) => q.status === 'PENDING'),
)

const passPercent = computed(() =>
  detail.value ? Math.round((detail.value.pass_rate ?? 0) * 100) : 0,
)
const passStatus = computed<'success' | 'warning'>(() =>
  detail.value && (detail.value.pass_rate ?? 0) >= 0.8 ? 'success' : 'warning',
)

/**
 * 题目在当前批次列表里的题号（即卡片徽标序号）。
 * 审核/重写对话框优先展示题号而非数据库 id，避免「列表第 4 题、弹窗却写 #43」的错位。
 */
function seqOf(q: Question | null): number {
  if (!q) return 0
  const idx = (detail.value?.questions ?? []).findIndex((x) => x.id === q.id)
  return idx >= 0 ? idx + 1 : 0
}
const rewriteSeq = computed(() => seqOf(rewriteQ.value))
const reviewSeq = computed(() => seqOf(reviewQ.value))

/** 全选待审（v-model） */
const allPendingSelected = computed({
  get: () => {
    const p = pendingQuestions.value
    return p.length > 0 && p.every((q) => selected.value.has(q.id))
  },
  set: (val: boolean) => {
    const next = new Set(selected.value)
    if (val) pendingQuestions.value.forEach((q) => next.add(q.id))
    else pendingQuestions.value.forEach((q) => next.delete(q.id))
    selected.value = next
  },
})

async function load(): Promise<void> {
  if (!batchId.value) return
  loading.value = true
  try {
    detail.value = await getBatchDetail(batchId.value)
    selected.value = new Set()
  } catch {
    // 404 等 message 已全局提示，退回批次列表
    router.push('/exam/ai/batches')
  } finally {
    loading.value = false
  }
}

watch(batchId, () => void load(), { immediate: true })

function clearSelection(): void {
  selected.value = new Set()
}

function toggleSelected(id: number, val: boolean): void {
  const next = new Set(selected.value)
  if (val) next.add(id)
  else next.delete(id)
  selected.value = next
}

function openReview(q: Question): void {
  reviewQ.value = q
  reviewAction.value = 'APPROVE'
  reviewNote.value = ''
  reviewVerified.value = q.interference_verified === 1
  reviewVisible.value = true
}

async function confirmReview(): Promise<void> {
  if (!reviewQ.value) return
  if (reviewAction.value === 'REJECT' && !reviewNote.value.trim()) {
    ElMessage.warning('驳回必须填写审核意见')
    return
  }
  reviewSubmitting.value = true
  try {
    await reviewQuestion(reviewQ.value.id, {
      action: reviewAction.value,
      review_note: reviewNote.value.trim() || null,
      interference_verified: reviewVerified.value,
    })
    ElMessage.success('审核完成')
    reviewVisible.value = false
    await load()
  } catch {
    // 后端 message 已提示
  } finally {
    reviewSubmitting.value = false
  }
}

function openRewrite(q: Question): void {
  rewriteQ.value = q
  rewriteFeedback.value = ''
  rewriteError.value = ''
  rewriteVisible.value = true
}

/** 从 axios 错误里提取后端 detail/message；超时/未知给引导文案 */
function rewriteFailText(e: unknown): string {
  if (e instanceof ApiError) return e.message
  const ax = e as {
    response?: { data?: { detail?: string; message?: string } }
    code?: string
  }
  const detail = ax.response?.data?.detail ?? ax.response?.data?.message
  if (detail) return String(detail)
  if (ax.code === 'ECONNABORTED' || ax.code === 'ETIMEDOUT') {
    return '请求超时：AI 可能仍在后台生成，请刷新本页查看本条是否已更新；若未更新，可稍后重试'
  }
  return 'AI 重写未完成，请调整修订要求后重试；若提示「已有已通过的修订版」，说明该题已被修订版取代，无需再重写'
}

async function confirmRewrite(): Promise<void> {
  if (!rewriteQ.value) return
  if (!rewriteFeedback.value.trim()) {
    ElMessage.warning('请填写修订要求')
    return
  }
  rewriteSubmitting.value = true
  try {
    await rewriteQuestion(rewriteQ.value.id, rewriteFeedback.value.trim())
    rewriteVisible.value = false
    // 就地替换语义：原题内容已覆盖并回到「待审核」，刷新当前批次即可原位看到修订结果（不新建批次）
    ElMessage.success('已重新生成，本条已就地更新并回到待审核')
    await load()
  } catch (e) {
    // 全局拦截器已 toast 具体原因（502 AI 重写失败 / 409 已存在修订版）；
    // 这里用对话框内常驻提示兜底，避免「以为生成了却找不到」。
    rewriteError.value = rewriteFailText(e)
  } finally {
    rewriteSubmitting.value = false
  }
}

function handleBatchApprove(): void {
  void doBatchReview('APPROVE')
}

function openBatchReject(): void {
  batchRejectNote.value = ''
  batchRejectVerified.value = false
  batchRejectVisible.value = true
}

function confirmBatchReject(): void {
  if (!batchRejectNote.value.trim()) {
    ElMessage.warning('整批驳回必须填写审核意见')
    return
  }
  batchRejectVisible.value = false
  void doBatchReview('REJECT')
}

async function doBatchReview(action: 'APPROVE' | 'REJECT'): Promise<void> {
  batchSubmitting.value = true
  try {
    const ids = selected.value.size > 0 ? [...selected.value] : undefined
    await reviewBatch(batchId.value, {
      action,
      review_note:
        action === 'REJECT' ? (batchRejectNote.value.trim() || null) : null,
      interference_verified:
        action === 'REJECT' ? batchRejectVerified.value : batchVerified.value,
      ids,
    })
    ElMessage.success(action === 'APPROVE' ? '批量通过完成' : '批量驳回完成')
    selected.value = new Set()
    await load()
  } catch {
    // 后端 message 已提示
  } finally {
    batchSubmitting.value = false
  }
}
</script>

<style scoped>
.batch-head {
  margin-bottom: 12px;
}
.head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.head-left {
  display: flex;
  align-items: center;
  gap: 6px;
}
.batch-id {
  font-size: 16px;
  font-weight: 600;
}
.batch-stats {
  margin-top: 4px;
}
.stat-pending {
  color: var(--el-color-warning);
  font-weight: 600;
}
.stat-approved {
  color: var(--el-color-success);
  font-weight: 600;
}
.stat-rejected {
  color: var(--el-color-danger);
  font-weight: 600;
}
.batch-bar {
  margin-bottom: 12px;
}
.batch-bar-inner {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.bar-spacer {
  flex: 1;
}
.question-list {
  display: flex;
  flex-direction: column;
}
.review-q-preview {
  margin-bottom: 14px;
  padding: 10px 12px;
  background: var(--surface);
  border-radius: 6px;
}
.review-q-content {
  margin-top: 8px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
}
.rewrite-origin {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.rewrite-error {
  margin: 8px 0;
}
.rewrite-hint {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}
.ml4 {
  margin-left: 8px;
}
</style>
