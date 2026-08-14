<template>
  <div class="result-page" v-loading="loading">
    <el-result v-if="notFound" icon="warning" title="记录不存在或无权限" subtitle="未找到该成绩单">
      <template #extra>
        <el-button type="primary" @click="router.replace('/exams')">返回选卷</el-button>
      </template>
    </el-result>

    <template v-else-if="result">
      <div class="page-head">
        <h2 class="page-title">{{ result.paper_name }} · 成绩单</h2>
      </div>

      <!-- 汇总 -->
      <el-card class="summary-card" shadow="never">
        <div class="summary-row">
          <div class="score-box">
            <div class="score-num" :class="result.passed ? 'pass' : 'fail'">{{ result.score }}</div>
            <div class="score-label">得分</div>
          </div>

          <div class="summary-item">
            <span class="label">试卷总分</span>
            <span class="value">{{ result.total_score }}</span>
          </div>

          <div class="summary-item">
            <span class="label">及格线</span>
            <span class="value">{{ result.pass_score }}</span>
          </div>

          <div class="summary-item">
            <span class="label">考试结果</span>
            <el-tag :type="result.passed ? 'success' : 'danger'" size="large" effect="dark">
              {{ result.passed ? '合格' : '不合格' }}
            </el-tag>
          </div>

          <div class="summary-item">
            <span class="label">交卷方式</span>
            <span class="value">{{ reasonText(result.reason) }}</span>
          </div>

          <div class="summary-item">
            <span class="label">切屏次数</span>
            <span class="value">{{ result.cheat_count }}</span>
          </div>

          <div class="summary-item">
            <span class="label">开始时间</span>
            <span class="value">{{ formatDateTime(result.start_time) }}</span>
          </div>

          <div class="summary-item">
            <span class="label">提交时间</span>
            <span class="value">{{ formatDateTime(result.submitted_at) }}</span>
          </div>

          <div class="summary-item">
            <span class="label">用时</span>
            <span class="value">{{ formatSeconds(result.duration * 60) }}</span>
          </div>
        </div>
      </el-card>

      <!-- 逐题 -->
      <div class="question-list">
        <el-card v-for="q in result.questions" :key="q.question_id" class="q-card" shadow="never">
          <div class="q-head">
            <el-tag size="small" :type="typeTag(q.type)">{{ questionTypeLabel(q.type) }}</el-tag>
            <span class="q-seq">第 {{ q.seq }} 题</span>
            <span class="q-score">{{ q.score }} 分</span>
            <el-tag v-if="q.is_correct" size="small" type="success">答对</el-tag>
            <el-tag v-else-if="q.type === 'SUBJECTIVE' && q.score > 0" size="small" type="warning">部分得分</el-tag>
            <el-tag v-else size="small" type="danger">答错</el-tag>
          </div>

          <div class="q-content" v-html="renderMarkdown(q.content)"></div>

          <div v-if="q.options && q.options.length" class="q-options">
            <div
              v-for="(opt, i) in q.options"
              :key="i"
              class="q-option"
              :class="optClass(q, opt, i)"
            >
              {{ opt }}
            </div>
          </div>

          <div class="q-answer">
            <span class="answer-item">
              我的作答：
              <b :class="q.is_correct ? 'text-ok' : 'text-bad'">{{ displayAnswer(q) }}</b>
            </span>
            <span class="answer-item">
              正确答案：
              <b class="text-ok">{{ q.correct_answer || '—' }}</b>
            </span>
          </div>

          <div class="q-analysis">
            <div class="analysis-title">解析</div>
            <div v-if="q.analysis" class="analysis-body" v-html="renderMarkdown(q.analysis)"></div>
            <div v-else class="analysis-body none">暂无解析</div>
          </div>
        </el-card>
      </div>

      <div class="result-foot">
        <el-button type="primary" @click="router.push('/exams')">返回考试列表</el-button>
        <el-button @click="router.push('/exams/records')">我的考试记录</el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getExamResult } from '@/api/exam'
import { ApiError } from '@/api/request'
import type { QuestionType, ResultSheet } from '@/types/models/exam'
import { questionTypeLabel } from '@/utils/constants/question'
import { formatDateTime, formatSeconds } from '@/utils/format'
import { renderMarkdown } from '@/utils/markdown'

const route = useRoute()
const router = useRouter()
const recordId = Number(route.params.recordId)

const loading = ref(true)
const notFound = ref(false)
const result = ref<ResultSheet | null>(null)

const REASON_MAP: Record<string, string> = {
  manual: '手动交卷',
  timeout: '时间到自动交卷',
  cheat_limit: '切屏超限自动交卷',
}

function reasonText(r: string | null | undefined): string {
  if (!r) return '—'
  return REASON_MAP[r] ?? r
}

function typeTag(t: QuestionType): 'primary' | 'success' | 'warning' | 'info' | 'danger' {
  switch (t) {
    case 'SINGLE':
      return 'primary'
    case 'MULTIPLE':
      return 'success'
    case 'JUDGE':
      return 'warning'
    case 'FILL':
      return 'info'
    case 'SUBJECTIVE':
      return 'danger'
  }
}

/** 选项 → 字母标签（与作答/判分口径一致） */
function optionValue(opt: string, idx: number): string {
  const first = opt.trim().charAt(0).toUpperCase()
  if (/^[A-H]$/.test(first)) return first
  return String.fromCharCode(65 + idx)
}

function isCorrectOpt(q: ResultSheet['questions'][number], opt: string, idx: number): boolean {
  const v = optionValue(opt, idx)
  return q.correct_answer
    .split(',')
    .map((s) => s.trim().toUpperCase())
    .includes(v)
}

function isUserOpt(q: ResultSheet['questions'][number], opt: string, idx: number): boolean {
  const v = optionValue(opt, idx)
  return q.user_answer
    .split(',')
    .map((s) => s.trim().toUpperCase())
    .includes(v)
}

function optClass(q: ResultSheet['questions'][number], opt: string, idx: number): string {
  const isCorrect = isCorrectOpt(q, opt, idx)
  const isUser = isUserOpt(q, opt, idx)
  if (q.is_correct) return isCorrect ? 'opt-ok' : ''
  // 答错：正确项标绿，用户误选项标红
  if (isCorrect) return 'opt-ok'
  if (isUser) return 'opt-bad'
  return ''
}

function displayAnswer(q: ResultSheet['questions'][number]): string {
  if (!q.user_answer) return '未作答'
  return q.user_answer
}

async function load() {
  loading.value = true
  try {
    const data = await getExamResult(recordId)
    result.value = data
  } catch (e) {
    // 400 尚未交卷 → 跳回作答页恢复
    const code = e instanceof ApiError ? e.code : (e as { response?: { status?: number } }).response?.status
    if (code === 400) {
      ElMessage.info('该考试尚未交卷，请继续作答')
      await router.replace(`/exams/${recordId}`)
      return
    }
    // 404 掩码 / 其他
    notFound.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.result-page {
  padding: 4px;
}

.page-head {
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.summary-card {
  border-radius: 10px;
  margin-bottom: 16px;
}

.summary-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 24px;
}

.score-box {
  text-align: center;
  padding-right: 24px;
  border-right: 1px solid var(--el-border-color-lighter);
}

.score-num {
  font-size: 34px;
  font-weight: 700;
  line-height: 1.2;
}

.score-num.pass {
  color: var(--el-color-success);
}

.score-num.fail {
  color: var(--el-color-danger);
}

.score-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 96px;
}

.summary-item .label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.summary-item .value {
  font-size: 15px;
  color: var(--el-text-color-primary);
  font-weight: 500;
}

.question-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.q-card {
  border-radius: 10px;
}

.q-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.q-seq {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.q-score {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.q-content {
  font-size: 15px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
}

.q-content :deep(p) {
  margin: 0 0 6px;
}

.q-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.q-option {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  background: #fafafa;
  color: var(--el-text-color-regular);
  line-height: 1.6;
  white-space: pre-wrap;
}

.q-option.opt-ok {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.q-option.opt-bad {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.q-answer {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  font-size: 14px;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
}

.answer-item .text-ok {
  color: var(--el-color-success);
}

.answer-item .text-bad {
  color: var(--el-color-danger);
}

.q-analysis {
  border-top: 1px dashed var(--el-border-color-lighter);
  padding-top: 10px;
}

.analysis-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin-bottom: 6px;
}

.analysis-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}

.analysis-body.none {
  color: #a5acaa;
}

.result-foot {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
