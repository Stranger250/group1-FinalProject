import type { QuestionDifficulty, QuestionStatus, QuestionType } from '@/types/models/exam'

/** 题型枚举（唯一真源） */
export const QUESTION_TYPES: { value: QuestionType; label: string; answerHint: string }[] = [
  { value: 'SINGLE', label: '单选题', answerHint: '选一个选项（如 A）' },
  { value: 'MULTIPLE', label: '多选题', answerHint: '多选，多个字母（如 ABD）' },
  { value: 'JUDGE', label: '判断题', answerHint: 'A=正确 / B=错误' },
  { value: 'FILL', label: '填空题', answerHint: '填写答案文本' },
]

/** 难度枚举（唯一真源） */
export const DIFFICULTIES: { value: QuestionDifficulty; label: string; tag: 'success' | 'warning' | 'danger' }[] = [
  { value: 'EASY', label: '简单', tag: 'success' },
  { value: 'MEDIUM', label: '中等', tag: 'warning' },
  { value: 'HARD', label: '困难', tag: 'danger' },
]

/** 题目状态枚举（唯一真源） */
export const QUESTION_STATUSES: { value: QuestionStatus; label: string; tag: 'info' | 'warning' | 'success' | 'danger' }[] = [
  { value: 'PENDING', label: '待审核', tag: 'warning' },
  { value: 'APPROVED', label: '已通过', tag: 'success' },
  { value: 'REJECTED', label: '已驳回', tag: 'danger' },
  { value: 'DISABLED', label: '已停用', tag: 'info' },
]

export function questionTypeLabel(v: QuestionType): string {
  return QUESTION_TYPES.find((x) => x.value === v)?.label ?? v
}

export function difficultyMeta(v: QuestionDifficulty) {
  return DIFFICULTIES.find((x) => x.value === v) ?? { value: v, label: v, tag: 'info' as const }
}

export function questionStatusMeta(v: QuestionStatus) {
  return QUESTION_STATUSES.find((x) => x.value === v) ?? { value: v, label: v, tag: 'info' as const }
}
