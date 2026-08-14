import dayjs from 'dayjs'

/** 日期时间格式：2026-08-13 14:30 */
export function formatDateTime(v: string | null | undefined): string {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : '-'
}

/** 日期格式：2026-08-13 */
export function formatDate(v: string | null | undefined): string {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD') : '-'
}

/** 相对时间：几分钟前 / 几小时前 / 日期 */
export function formatRelative(v: string | null | undefined): string {
  if (!v) return '-'
  const d = dayjs(v)
  if (!d.isValid()) return '-'
  const diff = dayjs().diff(d, 'minute')
  if (diff < 1) return '刚刚'
  if (diff < 60) return `${diff} 分钟前`
  if (diff < 60 * 24) return `${Math.floor(diff / 60)} 小时前`
  return d.format('MM-DD HH:mm')
}

/** 秒数 → mm:ss 或 h:mm:ss（考试倒计时） */
export function formatSeconds(total: number): string {
  const s = Math.max(0, Math.floor(total))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`
}

/** 百分比（0~1 → "80%"） */
export function percent(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return `${Math.round(v * 100)}%`
}
