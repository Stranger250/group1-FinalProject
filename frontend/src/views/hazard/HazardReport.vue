<!-- H01 隐患上报（P02）：单栏表单（描述/等级必填 + 位置/类型/标题可选 + 多图上传 ≤9）。
     AI 识别已拆分至「AI 分析」子菜单页；此处 onMounted 读取该页带回的结果自动回填表单，
     并随上报落 risk_report，可一键清除提示。 -->
<template>
  <div class="hazard-report">
    <div class="page-head">
      <h2 class="page-title">隐患上报</h2>
      <el-text type="info" size="small">发现安全隐患，请及时上报，管理员将跟进闭环</el-text>
    </div>

    <el-alert
      v-if="analysis"
      type="success"
      show-icon
      :closable="true"
      class="prefill-alert"
      title="已带入识别结果（来自「AI 分析」页）"
    >
      <div class="prefill-body">
        <span>等级：{{ hazardLevelMeta(analysis.level_suggest).label }} · 类型：{{ analysis.type_suggest || '未识别' }} · 置信度：{{ percent(analysis.confidence) }}</span>
        <el-button size="small" text type="primary" @click="clearAnalysis">清除回填</el-button>
      </div>
    </el-alert>

    <el-card shadow="never">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px" label-position="right">
        <el-form-item label="隐患描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="5"
            maxlength="2000"
            show-word-limit
            placeholder="请描述隐患的具体情况、位置与可能造成的后果"
          />
        </el-form-item>

        <el-form-item label="隐患等级" prop="level">
          <el-radio-group v-model="form.level">
            <el-radio v-for="l in HAZARD_LEVELS" :key="l.value" :value="l.value">
              <span class="level-option">
                <el-tag :type="l.tag" size="small">{{ l.label }}</el-tag>
                <span class="level-desc">{{ l.desc }}</span>
              </span>
            </el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="隐患位置" prop="location">
          <el-input v-model="form.location" maxlength="128" placeholder="如：3 号塔吊东侧基坑、二期综合楼 5 层（可选）" />
        </el-form-item>

        <el-form-item label="隐患类型" prop="type">
          <el-select
            v-model="form.type"
            placeholder="请选择类型或手动输入（可选）"
            clearable
            filterable
            allow-create
            style="width: 240px"
          >
            <el-option v-for="t in HAZARD_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>

        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" maxlength="128" placeholder="不填将自动截取描述前 20 字（可选）" />
        </el-form-item>

        <el-form-item label="现场图片" prop="images">
          <HazardImageUpload ref="imageUploadRef" v-model="form.images" :max="9" />
          <div class="upload-hint">最多上传 9 张，支持预览；建议上传清晰、能定位隐患的现场照片</div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" :icon="'Check'" @click="onSubmit">提交上报</el-button>
          <el-button @click="resetAll">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { createHazard } from '@/api/hazard'
import type { AnalyzeResult, HazardCreatePayload, HazardLevel } from '@/types/models/hazard'
import { HAZARD_LEVELS, HAZARD_TYPES, hazardLevelMeta } from '@/utils/constants'
import { percent } from '@/utils/format'
import { useHazardStore } from '@/store/hazard'
import HazardImageUpload from '@/components/hazard/HazardImageUpload.vue'

const router = useRouter()
const hazardStore = useHazardStore()

const formRef = ref<FormInstance>()
const form = reactive({
  title: '',
  description: '',
  location: '',
  level: '' as HazardLevel | '',
  type: '',
  images: [] as string[],
})

/** 「AI 分析」页带回的识别结果（回填表单 + 随上报落 risk_report） */
const analysis = ref<AnalyzeResult | null>(null)

const rules: FormRules = {
  description: [
    { required: true, message: '请填写隐患描述', trigger: 'blur' },
    { max: 2000, message: '描述最多 2000 字', trigger: 'blur' },
  ],
  level: [{ required: true, message: '请选择隐患等级', trigger: 'change' }],
}

// ---------- AI 识别结果回填 ----------
onMounted(() => {
  const { result, images } = hazardStore.consumeReportCarry()
  if (result) {
    analysis.value = result
    if (result.type_suggest) form.type = result.type_suggest
    if (result.level_suggest) form.level = result.level_suggest
    if (result.description && !form.description) form.description = result.description
  }
  // 带回 AI 分析页已上传的现场图片（避免再次上传）
  if (images.length && !form.images.length) form.images = images
})

/** 清除回填：仅清除提示与 risk_report 附带的识别信息，不重置已填表单 */
function clearAnalysis() {
  analysis.value = null
}

// ---------- 提交 ----------
const submitting = ref(false)

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (!form.images.length) {
    ElMessage.warning('请至少上传一张隐患图片')
    return
  }
  submitting.value = true
  try {
    const payload: HazardCreatePayload = {
      title: form.title.trim() || undefined,
      description: form.description.trim(),
      location: form.location.trim() || undefined,
      level: form.level as HazardLevel,
      type: form.type || undefined,
      images: form.images,
      risk_report: analysis.value ? { ...analysis.value } : null,
    }
    const detail = await createHazard(payload)
    ElMessage.success('隐患上报成功')
    router.push(`/hazards/${detail.id}`)
  } catch {
    // 业务/网络错误已由 request 层统一提示
  } finally {
    submitting.value = false
  }
}

function resetAll() {
  form.title = ''
  form.description = ''
  form.location = ''
  form.level = ''
  form.type = ''
  form.images = []
  analysis.value = null
  formRef.value?.clearValidate()
}
</script>

<style scoped>
.hazard-report {
  max-width: 960px;
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

.prefill-alert {
  margin-bottom: 16px;
}

.prefill-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.level-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.level-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary, #707a78);
}

.upload-hint {
  width: 100%;
  font-size: 12px;
  color: var(--el-text-color-placeholder, #a5acaa);
  margin-top: 6px;
}
</style>
