import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { AnalyzeResult } from '@/types/models/hazard'

/** 单图识别状态 */
export type AnalyzeStatus = 'pending' | 'running' | 'done' | 'failed'

/**
 * 模块一 隐患管理跨页状态。
 * - AI 分析页的图片/原始文件/逐图识别结果存于此：切到其他页面再回来不丢失，
 *   后台批量识别请求继续跑，完成后返回页面自动回显。
 * - 「将结果用于隐患上报」是一次性回填（result + 图片），上报页 onMounted 消费后即清空，避免下一个上报被串。
 * 页面内临时状态不入库，仅本次会话有效。
 */
export const useHazardStore = defineStore('hazard', () => {
  // ---- AI 分析页会话状态（跨页面保留）----
  /** 已上传图片 URL 列表 */
  const analyzeImages = ref<string[]>([])
  /** url → 原始 File（重进页面仍可复用识别）。注意：必须 return 给组件注入，否则子组件写不进。 */
  const analyzeFileMap = new Map<string, File>()
  /** url → 识别结果（多图逐张） */
  const analyzeResults = ref<Record<string, AnalyzeResult>>({})
  /** url → 识别状态 */
  const analyzeStatus = ref<Record<string, AnalyzeStatus>>({})
  /** 是否正在批量识别 */
  const analyzing = ref(false)
  /** 视觉服务不可用降级 */
  const aiDown = ref(false)

  function setAnalyzeImages(list: string[]): void {
    analyzeImages.value = list
  }
  function setAnalyzeFile(url: string, file: File): void {
    analyzeFileMap.set(url, file)
  }
  function deleteAnalyzeFile(url: string): void {
    analyzeFileMap.delete(url)
  }
  function getAnalyzeFile(url: string): File | undefined {
    return analyzeFileMap.get(url)
  }
  function setAnalyzeResult(url: string, r: AnalyzeResult): void {
    analyzeResults.value = { ...analyzeResults.value, [url]: r }
  }
  function deleteAnalyzeResult(url: string): void {
    const m = { ...analyzeResults.value }
    delete m[url]
    analyzeResults.value = m
  }
  function setAnalyzeStatus(url: string, s: AnalyzeStatus): void {
    analyzeStatus.value = { ...analyzeStatus.value, [url]: s }
  }
  function deleteAnalyzeStatus(url: string): void {
    const m = { ...analyzeStatus.value }
    delete m[url]
    analyzeStatus.value = m
  }
  function setAnalyzing(v: boolean): void {
    analyzing.value = v
  }
  function setAiDown(v: boolean): void {
    aiDown.value = v
  }
  /** 图片列表变化后清理已删除图片的孤儿识别状态 */
  function pruneAnalyzeState(urls: string[]): void {
    const keep = new Set(urls)
    const rs = { ...analyzeResults.value }
    const ss = { ...analyzeStatus.value }
    let changed = false
    for (const url of Object.keys(rs)) {
      if (!keep.has(url)) {
        delete rs[url]
        changed = true
      }
    }
    for (const url of Object.keys(ss)) {
      if (!keep.has(url)) {
        delete ss[url]
        changed = true
      }
    }
    if (changed) {
      analyzeResults.value = rs
      analyzeStatus.value = ss
    }
  }
  /** 清空 AI 分析页全部状态（清空图片按钮） */
  function resetAnalyze(): void {
    analyzeImages.value = []
    analyzeFileMap.clear()
    analyzeResults.value = {}
    analyzeStatus.value = {}
    analyzing.value = false
    aiDown.value = false
  }

  // ---- 上报页一次性回填（消费后即清空，防止下一条上报被串）----
  const latestAnalysis = ref<AnalyzeResult | null>(null)
  const reportImages = ref<string[]>([])

  function carryToReport(result: AnalyzeResult, images: string[]): void {
    latestAnalysis.value = result
    reportImages.value = [...images]
  }

  function consumeReportCarry(): { result: AnalyzeResult | null; images: string[] } {
    const result = latestAnalysis.value
    const images = [...reportImages.value]
    latestAnalysis.value = null
    reportImages.value = []
    return { result, images }
  }

  return {
    analyzeImages,
    analyzeFileMap,
    analyzeResults,
    analyzeStatus,
    analyzing,
    aiDown,
    setAnalyzeImages,
    setAnalyzeFile,
    deleteAnalyzeFile,
    getAnalyzeFile,
    setAnalyzeResult,
    deleteAnalyzeResult,
    setAnalyzeStatus,
    deleteAnalyzeStatus,
    setAnalyzing,
    setAiDown,
    pruneAnalyzeState,
    resetAnalyze,
    latestAnalysis,
    reportImages,
    carryToReport,
    consumeReportCarry,
  }
})
