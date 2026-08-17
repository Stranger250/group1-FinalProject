<!-- H01 隐患上报（O3 三段式整合）：① 图片区（上传+AI识别+标注图+保留勾选）→ ② 隐患区（等级/类型/子类/位置/标题/上报人）→ ③ 详细内容区（描述）。
     单页完成「传图 → 识别 → 确认（勾选保留）→ 提交」全流程；独立「AI 分析」页入口已移除（接口保留兼容）。 -->
<template>
  <div class="hazard-report">
    <div class="page-head">
      <h2 class="page-title">隐患上报</h2>
      <el-text type="info" size="small">发现安全隐患，请及时上报。支持 AI 识别辅助填写，管理员与安全员将跟进处理</el-text>
    </div>

    <!-- ① 图片区 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="section-title"><el-icon><Picture /></el-icon> 现场图片</span>
        <span class="section-hint">第一步：上传现场照片（最多 9 张）</span>
      </template>
      <HazardImageUpload ref="imageUploadRef" v-model="form.images" :max="9" />
      <div class="analyze-row">
        <el-button
          type="primary"
          plain
          :icon="'MagicStick'"
          :loading="analyzing"
          :disabled="!form.images.length"
          @click="onAnalyze"
        >
          AI 识别隐患
        </el-button>
        <el-text v-if="!form.images.length" type="info" size="small">上传图片后可一键识别隐患类型/等级/描述</el-text>
        <el-text v-else-if="analysis" type="success" size="small">
          已识别：{{ analysis.type_suggest || '未识别' }} · 置信度 {{ percent(analysis.confidence) }}
        </el-text>
      </div>
      <!-- 识别结果：标注图 + 摘要 + 保留勾选 -->
      <div v-if="analysis" class="analysis-block">
        <el-image
          v-if="analysis.annotated_url"
          :src="analysis.annotated_url"
          :preview-src-list="[analysis.annotated_url]"
          fit="contain"
          class="annotated-img"
        />
        <div class="analysis-meta">
          <div class="meta-line">
            <el-tag type="warning" size="small">{{ hazardLevelMeta(analysis.level_suggest).label }}</el-tag>
            <span class="meta-text">{{ analysis.description || '未生成描述' }}</span>
          </div>
          <el-checkbox v-model="keepRiskReport">保留 AI 识别结果（标注图与检测明细随上报保存；不勾选则仅保留原图）</el-checkbox>
          <el-button size="small" text type="primary" @click="clearAnalysis">清除识别结果</el-button>
        </div>
      </div>
    </el-card>

    <!-- ② 隐患区 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="section-title"><el-icon><Warning /></el-icon> 隐患概要</span>
        <span class="section-hint">第二步：填写隐患基本信息</span>
      </template>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px" label-position="right">
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

        <el-form-item label="隐患类型" prop="type">
          <div class="type-row">
            <el-select
              v-model="form.type"
              placeholder="选择大类（可选）"
              clearable
              filterable
              allow-create
              style="width: 180px"
              @change="onTypeChange"
            >
              <el-option v-for="t in categoryRoots" :key="t.name" :label="t.name" :value="t.name" />
            </el-select>
            <el-select
              v-model="form.subcategory"
              placeholder="选择子类（可选）"
              clearable
              filterable
              style="width: 220px"
              :disabled="!form.type"
            >
              <el-option
                v-for="s in currentSubcategories"
                :key="s.name"
                :label="s.check_items ? `${s.name}（${s.check_items}）` : s.name"
                :value="s.name"
              />
            </el-select>
          </div>
        </el-form-item>

        <el-form-item label="隐患位置" prop="location">
          <el-input v-model="form.location" maxlength="128" placeholder="如：3 号塔吊东侧基坑、二期综合楼 5 层（可选）" />
        </el-form-item>

        <el-form-item label="现场上报人" prop="reporter_name">
          <el-input v-model="form.reporter_name" maxlength="64" placeholder="默认当前登录用户，可填现场实际上报人" />
        </el-form-item>

        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" maxlength="128" placeholder="不填将自动截取描述前 20 字（可选）" />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ③ 详细内容区 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="section-title"><el-icon><Document /></el-icon> 详细内容</span>
        <span class="section-hint">第三步：描述隐患具体情况</span>
      </template>
      <el-form ref="detailFormRef" :model="form" :rules="rules" label-width="96px" label-position="right">
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
        <el-form-item>
          <el-button type="primary" :loading="submitting" :icon="'Check'" @click="onSubmit">提交上报</el-button>
          <el-button @click="resetAll">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { analyzeHazardImage, createHazard, listHazardCategories } from '@/api/hazard'
import type { AnalyzeResult, HazardCategoryNode, HazardCreatePayload, HazardLevel } from '@/types/models/hazard'
import { HAZARD_LEVELS, hazardLevelMeta } from '@/utils/constants'
import { percent } from '@/utils/format'
import { useHazardStore } from '@/store/hazard'
import { useUserStore } from '@/store/user'
import HazardImageUpload from '@/components/hazard/HazardImageUpload.vue'

const router = useRouter()
const userStore = useUserStore()
const hazardStore = useHazardStore()

const formRef = ref<FormInstance>()
const detailFormRef = ref<FormInstance>()
const form = reactive({
  title: '',
  description: '',
  location: '',
  level: '' as HazardLevel | '',
  type: '',
  subcategory: '',
  reporter_name: '',
  images: [] as string[],
})

// 默认现场上报人 = 当前登录用户姓名（可改，支持代报）
if (userStore.user?.name) form.reporter_name = userStore.user.name

/** AI 识别结果（回填表单 + 随上报落 risk_report） */
const analysis = ref<AnalyzeResult | null>(null)

/** 是否保留 AI 识别结果（B1：勾选保留 → risk_report 落库含 kept=true；不勾选 → 仅原图） */
const keepRiskReport = ref(true)

const analyzing = ref(false)

// O1 分类树：大类 → 子类
const categoryRoots = ref<HazardCategoryNode[]>([])
const currentSubcategories = computed(() => {
  const root = categoryRoots.value.find((r) => r.name === form.type)
  return root?.children ?? []
})
function onTypeChange() {
  form.subcategory = ''
}
async function loadCategories() {
  try {
    const res = await listHazardCategories()
    categoryRoots.value = res.items
  } catch {
    categoryRoots.value = []
  }
}

const rules: FormRules = {
  description: [
    { required: true, message: '请填写隐患描述', trigger: 'blur' },
    { max: 2000, message: '描述最多 2000 字', trigger: 'blur' },
  ],
  level: [{ required: true, message: '请选择隐患等级', trigger: 'change' }],
}

/** 单页 AI 识别：识别第一张图 → 回填类型/等级/描述 + 展示标注图 */
async function onAnalyze() {
  if (!form.images.length) return
  analyzing.value = true
  try {
    const res = (await analyzeHazardImage({ url: form.images[0] })).data
    analysis.value = res
    if (res.type_suggest && !form.type) form.type = res.type_suggest
    if (res.level_suggest) form.level = res.level_suggest
    if (res.description && !form.description) form.description = res.description
    keepRiskReport.value = true
  } catch {
    // 503 视觉降级：已由 request 层提示，用户可手动填写
  } finally {
    analyzing.value = false
  }
}

/** 清除识别：仅清除提示与 risk_report 附带信息，不重置已填表单 */
function clearAnalysis() {
  analysis.value = null
  keepRiskReport.value = true
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
      subcategory: form.subcategory.trim() || undefined,
      reporter_name: form.reporter_name.trim() || undefined,
      images: form.images,
      risk_report:
        analysis.value && keepRiskReport.value
          ? { ...analysis.value, kept: true }
          : null,
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
  form.subcategory = ''
  form.reporter_name = userStore.user?.name ?? ''
  form.images = []
  analysis.value = null
  keepRiskReport.value = true
  formRef.value?.clearValidate()
  detailFormRef.value?.clearValidate()
}

onMounted(() => {
  loadCategories()
  // 兼容旧入口：从「AI 分析」页跳转过来时带回的识别结果（老页面路由已移除，保留回填能力）
  const { result } = hazardStore.consumeReportCarry()
  if (result) {
    analysis.value = result
    if (result.type_suggest) form.type = result.type_suggest
    if (result.level_suggest) form.level = result.level_suggest
    if (result.description && !form.description) form.description = result.description
  }
})
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
.section-card {
  margin-bottom: 16px;
}
.section-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.section-hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
.analyze-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.analysis-block {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  padding: 12px;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 8px;
  flex-wrap: wrap;
}
.annotated-img {
  width: 260px;
  max-height: 180px;
  border-radius: 6px;
  flex-shrink: 0;
}
.analysis-meta {
  flex: 1;
  min-width: 240px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.meta-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.meta-text {
  font-size: 13px;
  color: var(--el-text-color-primary, #232b2a);
}
.type-row {
  display: flex;
  gap: 10px;
}
.level-option {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.level-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
</style>
