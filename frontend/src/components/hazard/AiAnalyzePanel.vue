<!-- 识别结果展示面板（H01）：标注图 + 汇总建议 + detections 编号列表。
     详情页只读（actionable=false）；上报页传 actionable 显示「应用到表单」。
     视觉：去「AI demo」观感——单色黛青编号、暖纸面底、工程语气文案。 -->
<template>
  <div class="ai-analyze-panel">
    <div v-if="result.annotated_url" class="annotated-block">
      <div class="panel-label">识别标注图</div>
      <el-image
        class="annotated-img"
        :src="result.annotated_url"
        fit="contain"
        :preview-src-list="[result.annotated_url]"
        preview-teleported
      />
    </div>

    <div class="summary-card">
      <div class="panel-label">识别建议</div>
      <div class="summary-grid">
        <div class="summary-item">
          <span class="k">隐患类型</span>
          <span class="v">{{ result.type_suggest || '未识别' }}</span>
        </div>
        <div class="summary-item">
          <span class="k">建议等级</span>
          <el-tag :type="levelMeta.tag">{{ levelMeta.label }}</el-tag>
        </div>
        <div class="summary-item">
          <span class="k">置信度</span>
          <span class="v">{{ percent(result.confidence) }}</span>
        </div>
      </div>
      <div v-if="result.reason" class="reason-line">
        <span class="k">判断依据</span>
        <span class="v">{{ result.reason }}</span>
      </div>
      <div v-if="result.description" class="desc-block">
        <div class="panel-sub">图片描述</div>
        <p class="desc-text">{{ result.description }}</p>
      </div>
    </div>

    <div v-if="result.detections && result.detections.length" class="detections-block">
      <div class="panel-label">识别明细（{{ result.detections.length }} 处）</div>
      <ul class="detections-list">
        <li v-for="(d, i) in result.detections" :key="i" class="detection-item">
          <span class="dot">{{ i + 1 }}</span>
          <div class="det-body">
            <div class="det-head">
              <span class="det-type">{{ d.type || d.type_suggest || '未识别' }}</span>
              <el-tag :type="detLevelMeta(d.level || d.level_suggest).tag" size="small">{{ detLevelMeta(d.level || d.level_suggest).label }}</el-tag>
              <span class="det-conf">{{ percent(d.confidence) }}</span>
            </div>
            <p class="det-desc">{{ d.description }}</p>
            <p v-if="d.reason" class="det-reason">判断依据：{{ d.reason }}</p>
          </div>
        </li>
      </ul>
    </div>

    <div v-if="actionable" class="panel-actions">
      <el-button type="primary" @click="emit('apply')">应用到表单</el-button>
      <el-text type="info" size="small">识别结果供参考，请结合现场情况确认后提交</el-text>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AnalyzeResult, HazardLevel } from '@/types/models/hazard'
import { hazardLevelMeta } from '@/utils/constants'
import { percent } from '@/utils/format'

const props = withDefaults(defineProps<{ result: AnalyzeResult; actionable?: boolean }>(), {
  actionable: false,
})
const emit = defineEmits<{ (e: 'apply'): void }>()

const levelMeta = computed(() => hazardLevelMeta(props.result.level_suggest))

function detLevelMeta(level: string | undefined) {
  return hazardLevelMeta((level || 'MINOR') as HazardLevel)
}
</script>

<style scoped>
.ai-analyze-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: var(--surface, #f8f7f3);
  border: 1px solid var(--el-border-color-light, #e5e1d7);
  border-radius: 6px;
}

.panel-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary, #232b2a);
  margin-bottom: 8px;
}

.panel-sub {
  font-size: 13px;
  color: var(--el-text-color-secondary, #707a78);
  margin: 8px 0 4px;
}

.annotated-img {
  width: 100%;
  max-height: 360px;
  border-radius: 6px;
  background: var(--page-bg, #f6f5f1);
  cursor: zoom-in;
}

.summary-card {
  border: 1px solid var(--el-border-color-lighter, #ece8df);
  border-radius: 6px;
  padding: 10px 12px;
  background: #fff;
}

.summary-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  align-items: center;
}

.summary-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.summary-item .k,
.reason-line .k {
  color: var(--el-text-color-secondary, #707a78);
}

.summary-item .v,
.reason-line .v {
  color: var(--el-text-color-primary, #232b2a);
}

.reason-line {
  margin-top: 8px;
  font-size: 13px;
  display: flex;
  gap: 8px;
}

.desc-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular, #4b5553);
  white-space: pre-wrap;
}

.detections-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detection-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter, #ece8df);
  border-radius: 6px;
}

/* 编号方块：黛青单色系（替代彩虹七色），与标注图编号保持一致 */
.dot {
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: var(--brand-soft, #e6efed);
  color: var(--brand, #1e5a52);
  font-size: 12px;
  font-weight: 600;
  line-height: 20px;
  text-align: center;
}

.det-body {
  min-width: 0;
  flex: 1;
}

.det-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.det-type {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary, #232b2a);
}

.det-conf {
  font-size: 12px;
  color: var(--el-text-color-secondary, #707a78);
}

.det-desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--el-text-color-regular, #4b5553);
}

.det-reason {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--el-text-color-placeholder, #a5acaa);
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 4px;
}
</style>
