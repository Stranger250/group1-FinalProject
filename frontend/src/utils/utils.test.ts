import { describe, expect, it } from 'vitest'
import { formatDateTime, formatDate, formatRelative, formatSeconds, percent } from '@/utils/format'
import { validateImage } from '@/utils/validate'
import { cleanParams } from '@/api/request'

describe('format', () => {
  it('formatDateTime：空值/非法 → "-"', () => {
    expect(formatDateTime(null)).toBe('-')
    expect(formatDateTime(undefined)).toBe('-')
    expect(formatDateTime('not-a-date')).toBe('-')
  })

  it('formatDateTime：合法 ISO → YYYY-MM-DD HH:mm', () => {
    expect(formatDateTime('2026-08-13T14:30:00')).toBe('2026-08-13 14:30')
  })

  it('formatDate：合法 → YYYY-MM-DD', () => {
    expect(formatDate('2026-08-13T08:00:00')).toBe('2026-08-13')
    expect(formatDate('')).toBe('-')
  })

  it('formatSeconds：倒计时 mm:ss / h:mm:ss，负数钳 0', () => {
    expect(formatSeconds(0)).toBe('00:00')
    expect(formatSeconds(65)).toBe('01:05')
    expect(formatSeconds(3661)).toBe('1:01:01')
    expect(formatSeconds(-5)).toBe('00:00')
  })

  it('percent：0~1 → 百分比，null/undefined → "-"', () => {
    expect(percent(0.8)).toBe('80%')
    expect(percent(0)).toBe('0%')
    expect(percent(1)).toBe('100%')
    expect(percent(null)).toBe('-')
    expect(percent(undefined)).toBe('-')
  })
})

describe('formatRelative', () => {
  it('刚刚 / 分钟前 / 小时前 / 日期回退', () => {
    const now = new Date()
    expect(formatRelative(now.toISOString())).toBe('刚刚')
    const m5 = new Date(now.getTime() - 5 * 60 * 1000)
    expect(formatRelative(m5.toISOString())).toBe('5 分钟前')
    const h2 = new Date(now.getTime() - 2 * 60 * 60 * 1000)
    expect(formatRelative(h2.toISOString())).toMatch(/小时前/)
    expect(formatRelative(null)).toBe('-')
    expect(formatRelative('bad')).toBe('-')
  })
})

describe('validateImage（PRD B03 前端预校验）', () => {
  const makeFile = (name: string, size: number): File =>
    new File([new Uint8Array(size)], name, { type: 'image/jpeg' })

  it('合法 jpg/jpeg/png（大小内）→ null', () => {
    expect(validateImage(makeFile('a.jpg', 100))).toBeNull()
    expect(validateImage(makeFile('a.JPEG', 100))).toBeNull()
    expect(validateImage(makeFile('a.png', 100))).toBeNull()
  })

  it('非法扩展名 → 错误文案', () => {
    expect(validateImage(makeFile('a.exe', 100))).toMatch(/仅支持 jpg\/png\/jpeg/)
    expect(validateImage(makeFile('a.txt', 100))).toMatch(/仅支持/)
    expect(validateImage(makeFile('', 100))).toMatch(/未知/)
  })

  it('超过 5MB → 大小错误', () => {
    expect(validateImage(makeFile('big.jpg', 5 * 1024 * 1024 + 1))).toMatch(/大小上限/)
  })
})

describe('cleanParams（过滤空参）', () => {
  it('剔除 undefined/null/空串，保留 0/false/非空', () => {
    expect(cleanParams({ a: undefined, b: null, c: '', d: 0, e: false, f: 'x', g: ' ' })).toEqual({
      d: 0,
      e: false,
      f: 'x',
      g: ' ',
    })
  })

  it('空对象 → 空对象', () => {
    expect(cleanParams({})).toEqual({})
  })
})
