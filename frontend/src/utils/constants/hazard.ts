import type { HazardLevel, HazardStatus } from '@/types/models/hazard'

/** 隐患等级枚举（唯一真源，对齐 DATABASE.md §4.1） */
export const HAZARD_LEVELS: { value: HazardLevel; label: string; tag: 'danger' | 'warning' | 'primary' | 'info'; desc: string }[] = [
  { value: 'CRITICAL', label: '重大', tag: 'danger', desc: '可能导致重大安全事故，需立即整改' },
  { value: 'MAJOR', label: '较大', tag: 'warning', desc: '可能导致较大安全事故，限期整改' },
  { value: 'GENERAL', label: '一般', tag: 'primary', desc: '一般性问题，常规整改' },
  { value: 'MINOR', label: '轻微', tag: 'info', desc: '轻微问题，建议整改' },
]

/** 隐患状态枚举（唯一真源） */
export const HAZARD_STATUSES: { value: HazardStatus; label: string; tag: 'info' | 'danger' | 'warning' | 'success' }[] = [
  { value: 'WAIT_PROCESS', label: '待处理', tag: 'danger' },
  { value: 'PROCESSING', label: '处理中', tag: 'warning' },
  { value: 'WAIT_CHECK', label: '待验收', tag: 'warning' },
  { value: 'FINISHED', label: '已闭环', tag: 'success' },
  { value: 'REJECTED', label: '已驳回', tag: 'info' },
]

/** 隐患类型（对齐 HazardType） */
export const HAZARD_TYPES = ['高处作业', '用电安全', '机械伤害', '消防', '临边防护', '其他'] as const

export function hazardLevelMeta(v: HazardLevel) {
  return HAZARD_LEVELS.find((x) => x.value === v) ?? { value: v, label: v, tag: 'info' as const, desc: '' }
}

export function hazardStatusMeta(v: HazardStatus) {
  return HAZARD_STATUSES.find((x) => x.value === v) ?? { value: v, label: v, tag: 'info' as const }
}
