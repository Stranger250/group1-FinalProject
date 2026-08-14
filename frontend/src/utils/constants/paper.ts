import type { PaperGenMode, PaperStatus } from '@/types/models/exam'

/** 试卷状态枚举（唯一真源） */
export const PAPER_STATUSES: { value: PaperStatus; label: string; tag: 'info' | 'success' | 'danger' }[] = [
  { value: 'DRAFT', label: '草稿', tag: 'info' },
  { value: 'PUBLISHED', label: '已发布', tag: 'success' },
  { value: 'DISABLED', label: '已停用', tag: 'danger' },
]

/** 组卷方式枚举 */
export const PAPER_GEN_MODES: { value: PaperGenMode; label: string }[] = [
  { value: 'manual', label: '手动组卷' },
  { value: 'ai', label: 'AI 智能组卷' },
]

/** 考试时长档位（PRD E03 固定三档） */
export const PAPER_DURATIONS = [
  { value: 30, label: '30 分钟' },
  { value: 60, label: '60 分钟' },
  { value: 90, label: '90 分钟' },
] as const

export function paperStatusMeta(v: PaperStatus) {
  return PAPER_STATUSES.find((x) => x.value === v) ?? { value: v, label: v, tag: 'info' as const }
}

export function paperGenModeLabel(v: PaperGenMode): string {
  return PAPER_GEN_MODES.find((x) => x.value === v)?.label ?? v
}
