<!-- H01 隐患上报 · AI 分析（子菜单独立页）：上传多张现场图 → 「识别全部」批量逐张 AI 识别 →
     每张图一个识别结果（标注图/检测明细），可单独带入「隐患上报」。
     图片/识别过程/结果均存于 hazard store：切换页面不丢失，后台识别完成后返回页面自动回显。
     AI 不可用（503）降级提示，不影响手动上报。 -->
<template>
  <div class="hazard-analyze">
    <div class="page-head">
      <h2 class="page-title">智能识别</h2>
      <el-text type="info" size="small">上传隐患现场图片，自动识别隐患类型、等级与位置，识别结果可带入隐患上报</el-text>
    </div>

    <div class="analyze-layout">
      <!-- 左栏：图片 + 识别操作 -->
      <div class="analyze-left">
        <el-card shadow="never">
          <template #header>
            <span class="card-title">现场图片</span>
          </template>

          <HazardImageUpload
            v-model="hazardStore.analyzeImages"
            :files="hazardStore.analyzeFileMap"
            :max="9"
          />
          <div class="upload-hint">最多上传 9 张，jpg/png/jpeg ≤5MB；上传后点击「识别全部」批量识别每张图片</div>

          <div class="analyze-actions">
            <el-button
              type="primary"
              :icon="'MagicStick'"
              :loading="hazardStore.analyzing"
              :disabled="!hazardStore.analyzeImages.length"
              @click="onAnalyzeAll"
            >
              识别全部
            </el-button>
            <el-button v-if="doneCount" :disabled="hazardStore.analyzing" @click="onAnalyzeAll">重新识别</el-button>
            <el-button :disabled="!hazardStore.analyzeImages.length || hazardStore.analyzing" @click="clearAll">
              清空图片
            </el-button>
          </div>
        </el-card>
      </div>

      <!-- 右栏：识别结果（逐图） -->
      <div class="analyze-right">
        <el-card shadow="never">
          <template #header>
            <div class="result-head">
              <span class="card-title">识别结果</span>
              <el-tag v-if="doneCount" type="success" size="small">完成 {{ doneCount }}/{{ imageItems.length }}</el-tag>
            </div>
          </template>

          <el-alert
            v-if="hazardStore.aiDown"
            type="warning"
            show-icon
            :closable="false"
            title="视觉识别不可用，已中止后续识别；不影响手动隐患上报"
            class="ai-alert"
          />

          <div v-if="hazardStore.analyzing" class="analyze-progress">
            <el-progress :percentage="progressPercent" :stroke-width="8" />
            <el-text type="info" size="small">正在识别第 {{ runningIndex }} 张，请稍候…</el-text>
          </div>

          <template v-else-if="hasResult">
            <div class="result-list">
              <template v-for="(item, idx) in imageItems" :key="item.url">
                <div v-if="item.status === 'pending'" class="result-card pending">
                  <el-image class="result-thumb" :src="item.url" fit="cover" />
                  <span class="result-label">图片 {{ idx + 1 }} · 等待识别</span>
                </div>

                <div v-else-if="item.status === 'failed'" class="result-card failed">
                  <el-image class="result-thumb" :src="item.url" fit="cover" />
                  <div class="failed-body">
                    <span class="result-label">图片 {{ idx + 1 }}</span>
                    <el-tag type="danger" size="small">识别失败</el-tag>
                  </div>
                </div>

                <div v-else-if="item.result" class="result-card">
                  <div class="result-card-head">
                    <el-image class="result-thumb" :src="item.url" fit="cover" />
                    <span class="result-label">图片 {{ idx + 1 }}</span>
                    <el-tag type="success" size="small">已识别</el-tag>
                  </div>
                  <AiAnalyzePanel :result="item.result" />
                  <div class="result-card-actions">
                    <el-button type="primary" size="small" :icon="'EditPen'" @click="applyToReport(item.result!)">
                      将结果用于隐患上报
                    </el-button>
                    <el-text type="info" size="small">带入等级 / 类型 / 描述及全部现场图片</el-text>
                  </div>
                </div>
              </template>
            </div>
          </template>

          <el-empty v-else :image-size="88" description="请先上传图片并点击「识别全部」">
            <template #description>
              <span>识别结果将显示在这里</span>
            </template>
          </el-empty>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { analyzeHazardImage } from '@/api/hazard'
import type { AnalyzeResult } from '@/types/models/hazard'
import { useHazardStore } from '@/store/hazard'
import HazardImageUpload from '@/components/hazard/HazardImageUpload.vue'
import AiAnalyzePanel from '@/components/hazard/AiAnalyzePanel.vue'

const router = useRouter()
const hazardStore = useHazardStore()

/** 逐图展示行：url + 结果 + 状态 */
const imageItems = computed(() =>
  hazardStore.analyzeImages.map((url) => ({
    url,
    result: hazardStore.analyzeResults[url] ?? null,
    status: hazardStore.analyzeStatus[url] ?? 'pending',
  })),
)
const doneCount = computed(() => imageItems.value.filter((i) => i.status === 'done').length)
const hasResult = computed(() => imageItems.value.some((i) => i.status !== 'pending') && !hazardStore.analyzing)
const progressPercent = computed(() =>
  imageItems.value.length ? Math.round((doneCount.value / imageItems.value.length) * 100) : 0,
)
const runningIndex = computed(() => {
  const idx = imageItems.value.findIndex((i) => i.status === 'running')
  return idx === -1 ? doneCount.value + 1 : idx + 1
})

/** 图片列表变化：清理已删除图片的孤儿识别状态 */
watch(
  () => hazardStore.analyzeImages,
  (list) => hazardStore.pruneAnalyzeState(list),
)

function is503Error(e: unknown): boolean {
  return (e as { response?: { status?: number } })?.response?.status === 503
}

/** 批量识别全部图片（顺序执行；503 立即中止后续） */
async function onAnalyzeAll() {
  const urls = hazardStore.analyzeImages
  if (!urls.length) {
    ElMessage.warning('请先上传现场图片')
    return
  }
  for (const url of urls) hazardStore.setAnalyzeStatus(url, 'pending')
  hazardStore.setAiDown(false)
  hazardStore.setAnalyzing(true)

  let done = 0
  let failed = 0
  for (const url of urls) {
    hazardStore.setAnalyzeStatus(url, 'running')
    const file = hazardStore.getAnalyzeFile(url)
    if (!file) {
      hazardStore.setAnalyzeStatus(url, 'failed')
      failed++
      continue
    }
    try {
      const res = await analyzeHazardImage(file)
      if (res.code === 200) {
        hazardStore.setAnalyzeResult(url, res.data)
        hazardStore.setAnalyzeStatus(url, 'done')
        done++
      } else {
        hazardStore.setAnalyzeStatus(url, 'failed')
        failed++
        if (res.code === 503) {
          hazardStore.setAiDown(true)
          break
        }
      }
    } catch (e) {
      hazardStore.setAnalyzeStatus(url, 'failed')
      failed++
      if (is503Error(e)) {
        hazardStore.setAiDown(true)
        break
      }
    }
  }
  hazardStore.setAnalyzing(false)
  if (failed) ElMessage.warning(`识别完成：成功 ${done} 张，失败 ${failed} 张`)
  else ElMessage.success(`识别完成：成功 ${done} 张`)
}

function clearAll() {
  hazardStore.resetAnalyze()
}

/** 携带该图识别结果 + 全部现场图片跳转隐患上报页（上报页 onMounted 消费并回填） */
function applyToReport(result: AnalyzeResult) {
  hazardStore.carryToReport(result, hazardStore.analyzeImages)
  ElMessage.success('已带入识别结果与现场图片，请在上报页核对后提交')
  router.push('/hazards/report')
}
</script>

<style scoped>
.hazard-analyze {
  max-width: 1180px;
  margin: 0 auto;
}

.page-head {
  margin-bottom: 16px;
}

.page-title {
  margin: 0 0 4px;
  font-size: 20px;
  color: var(--el-text-color-primary, #232b2a);
}

.analyze-layout {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.analyze-left {
  flex: 1;
  min-width: 0;
}

.analyze-right {
  flex: none;
  width: 480px;
  position: sticky;
  top: 16px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary, #232b2a);
}

.upload-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder, #a5acaa);
  margin: 6px 0 12px;
}

.analyze-actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ai-alert {
  margin-bottom: 12px;
}

.analyze-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-card {
  border: 1px solid var(--el-border-color-lighter, #ece8df);
  border-radius: 6px;
  padding: 12px;
  background: var(--surface, #f8f7f3);
}

.result-card.pending {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--el-text-color-secondary, #707a78);
  font-size: 13px;
}

.result-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.result-thumb {
  flex: none;
  width: 56px;
  height: 56px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-light, #e5e1d7);
  background: var(--page-bg, #f6f5f1);
}

.result-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary, #232b2a);
}

.result-card-actions {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--el-border-color-lighter, #ece8df);
  display: flex;
  align-items: center;
  gap: 12px;
}

.result-card.failed {
  display: flex;
  align-items: center;
  gap: 10px;
}

.failed-body {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

@media (max-width: 1080px) {
  .analyze-layout {
    flex-direction: column;
  }

  .analyze-right {
    width: 100%;
    position: static;
  }
}
</style>
