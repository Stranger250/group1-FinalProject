<template>
  <div class="question-card">
    <el-card shadow="hover" :body-style="{ padding: '14px 16px' }">
      <div class="qc-head">
        <div class="qc-head-tags">
          <span v-if="seq" class="qc-seq">{{ seq }}</span>
          <el-tag size="small" effect="plain">{{ typeLabel }}</el-tag>
          <el-tag size="small" :type="diffMeta.tag" effect="plain">{{ diffMeta.label }}</el-tag>
          <el-tag v-if="!paperPreview" size="small" :type="statusMeta.tag">{{ statusMeta.label }}</el-tag>
          <el-tag v-if="score != null" size="small" type="warning" effect="plain">{{ score }} 分</el-tag>
          <el-tag
            v-if="!paperPreview && question.source === 'ai'"
            size="small"
            type="primary"
            effect="plain"
          >
            智能生成
          </el-tag>
          <el-tag
            v-if="!paperPreview && question.interference_verified === 1"
            size="small"
            type="success"
            effect="plain"
          >
            已核对干扰项
          </el-tag>
        </div>
        <div class="qc-head-ops">
          <!-- 框选仅用于批量操作选择；单题操作（审核/AI 重写）在卡片底部 .qc-actions，避免与框选混淆 -->
          <el-checkbox v-if="selectable" v-model="checked" class="qc-select" @click.stop>
            <span class="qc-select-label">选择</span>
          </el-checkbox>
        </div>
      </div>

      <div class="qc-content markdown-body" v-html="renderMarkdown(question.content)" />

      <div v-if="question.type !== 'FILL' && optionList.length" class="qc-options">
        <div v-for="(opt, i) in optionList" :key="i" class="qc-option">
          <span class="qc-opt-letter">{{ optionLetter(opt) || String.fromCharCode(65 + i) }}</span>
          <span class="qc-opt-text">{{ optionBody(opt) }}</span>
        </div>
      </div>

      <div v-if="showAnswer" class="qc-answer">
        <div class="qc-answer-line">
          <span class="qc-label">答案：</span>
          <span>{{ answerText }}</span>
        </div>
        <div v-if="question.analysis" class="qc-analysis">
          <span class="qc-label">解析：</span>
          <span class="markdown-body" v-html="renderMarkdown(question.analysis)" />
        </div>
        <div v-if="question.review_note" class="qc-review-note">
          <span class="qc-label">审核意见：</span>
          <span>{{ question.review_note }}</span>
        </div>
        <div v-if="question.rewrite_of" class="qc-rewrite-note">
          <span class="qc-label">重写：</span>
          <span>本题由题 #{{ question.rewrite_of }} 重写生成</span>
        </div>
        <div v-if="question.rewrite_feedback" class="qc-rewrite-note">
          <span class="qc-label">修订要求：</span>
          <span>{{ question.rewrite_feedback }}</span>
        </div>
      </div>

      <div v-if="showAnswer && sourceLines.length" class="qc-source">
        <span class="qc-label">溯源：</span>
        <div class="qc-source-lines">
          <div v-for="(line, i) in sourceLines" :key="i" class="qc-source-line">{{ line }}</div>
        </div>
      </div>

      <div v-if="question.knowledge_point" class="qc-kp">
        <span class="qc-label">知识点：</span>
        <span>{{ question.knowledge_point }}</span>
      </div>

      <!-- 单题操作（审核 / AI 重写 等）：独立成底部栏，与头部批量框选视觉分离 -->
      <div v-if="$slots.actions" class="qc-actions">
        <slot name="actions" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { difficultyMeta, questionStatusMeta, questionTypeLabel } from '@/utils/constants'
import type { Question } from '@/types/models/exam'

const props = withDefaults(
  defineProps<{
    question: Question
    /** 是否展示答案/解析/溯源（审核与预览场景默认展示） */
    showAnswer?: boolean
    /** 是否展示多选勾选框（批次批量审核场景） */
    selectable?: boolean
    /** 卡片序号（如试卷内题序 seq） */
    seq?: number | string
    /** 分值（试卷内展示） */
    score?: number | null
    /** 试卷预览模式：隐藏状态/AI 来源/干扰项核对等管理侧标签 */
    paperPreview?: boolean
  }>(),
  {
    showAnswer: true,
    selectable: false,
    seq: undefined,
    score: null,
    paperPreview: false,
  },
)

/** 批量选择绑定（v-model:checked） */
const checked = defineModel<boolean>('checked', { default: false })

const typeLabel = computed(() => questionTypeLabel(props.question.type))
const diffMeta = computed(() => difficultyMeta(props.question.difficulty))
const statusMeta = computed(() => questionStatusMeta(props.question.status))

/** 选项列表（判断题固定 A 正确 / B 错误） */
const optionList = computed<string[]>(() => {
  if (props.question.type === 'JUDGE') return ['A 正确', 'B 错误']
  return props.question.options ?? []
})

/** 提取选项字母前缀（兼容 "A. xxx" / "A xxx" / "A"） */
function optionLetter(opt: string): string {
  const m = opt.match(/^([A-Za-z])[.、．)）\s:：]/)
  return m ? m[1].toUpperCase() : ''
}

/** 去掉选项字母前缀的正文 */
function optionBody(opt: string): string {
  const m = opt.match(/^[A-Za-z][.、．)）\s:：]*\s?(.*)$/)
  return m ? m[1] : opt
}

const answerText = computed<string>(() => {
  const q = props.question
  if (q.type === 'JUDGE') {
    const a = q.answer.trim().toUpperCase()
    if (a === 'A') return 'A（正确）'
    if (a === 'B') return 'B（错误）'
    return q.answer
  }
  if (q.type === 'MULTIPLE') {
    return q.answer
      .split(/[,，]/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean)
      .join('、')
  }
  if (q.type === 'FILL') {
    return q.answer.replace(/[;；]/g, '；')
  }
  return q.answer
})

const ROLE_LABELS: Record<string, string> = {
  answer: '答案来源',
  distractor: '干扰项来源',
  analysis: '解析来源',
}

const sourceLines = computed<string[]>(() => {
  const lines: string[] = []
  for (const s of props.question.sources ?? []) {
    const role = ROLE_LABELS[s.role] ?? s.role
    const ref = [s.law_title, s.article_no ? `第${s.article_no}条` : ''].filter(Boolean).join(' · ')
    lines.push(ref ? `${role}：${ref}` : role)
  }
  if (props.question.source_law_title) {
    const ref = [props.question.source_law_title, props.question.source_article_no ? `第${props.question.source_article_no}条` : '']
      .filter(Boolean)
      .join(' · ')
    lines.push(`出处：${ref}`)
  }
  return lines
})
</script>

<style scoped>
.question-card {
  margin-bottom: 12px;
}
.question-card :deep(.el-card) {
  border-radius: 10px;
}
.question-card :deep(.el-card.is-hover-shadow:hover) {
  box-shadow: 0 1px 2px rgba(23, 45, 43, 0.05), 0 4px 12px rgba(23, 45, 43, 0.06);
}
.qc-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.qc-head-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.qc-head-tags .el-tag {
  margin-right: 0;
}
.qc-head-ops {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
/* 框选控件：黛青描边 + 「选择」文字标签，让批量选择入口一眼可见
   （Element Plus 默认灰框在白色卡片上太淡，且无标签易被忽略） */
.qc-select {
  margin-right: 0;
}
.qc-select :deep(.el-checkbox__inner) {
  width: 17px;
  height: 17px;
  border-color: var(--el-color-primary-light-5);
}
.qc-select :deep(.el-checkbox__inner::after) {
  width: 4px;
  height: 8px;
  border-width: 2px;
}
.qc-select :deep(.el-checkbox__input:hover .el-checkbox__inner),
.qc-select :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary);
}
.qc-select-label {
  margin-left: 2px;
  font-size: 12px;
  color: var(--el-color-primary);
  user-select: none;
}
.qc-select :deep(.el-checkbox__input.is-checked) + .el-checkbox__label .qc-select-label {
  font-weight: 600;
}
.qc-seq {
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-right: 4px;
}
.qc-content {
  font-size: 15px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.qc-options {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.qc-option {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.qc-opt-letter {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: var(--brand-soft);
  color: var(--el-color-primary);
  font-weight: 600;
  text-align: center;
  line-height: 20px;
  font-size: 13px;
}
.qc-opt-text {
  line-height: 1.6;
  word-break: break-word;
}
.qc-answer {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f8f9fb;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--el-text-color-regular);
}
.qc-answer-line {
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.qc-label {
  color: var(--el-text-color-secondary);
}
.markdown-body :deep(p) {
  margin: 0;
}
.markdown-body :deep(p + p) {
  margin-top: 6px;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}
.qc-source {
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: flex;
  gap: 6px;
}
.qc-source-lines {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.qc-kp {
  margin-top: 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.qc-review-note,
.qc-rewrite-note {
  margin-top: 6px;
}
/* 底部单题操作栏：顶部细分隔线与卡片内容分开，明确是可直接点击的单题操作 */
.qc-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 4px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
