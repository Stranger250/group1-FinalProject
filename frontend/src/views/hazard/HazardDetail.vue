<!-- H03-H06 隐患详情（P04）：全字段 + 图片 + 时间线 + AI 识别报告
     处理操作（SAFETY/ADMIN + 状态门控）：派单（WAIT_PROCESS）/ 整改（PROCESSING）/ 验收（WAIT_CHECK）/ 一键闭环（WAIT_PROCESS）。 -->
<template>
  <div class="hazard-detail">
    <div v-if="loading" v-loading="true" class="detail-loading" />

    <template v-else-if="detail">
      <div class="page-head">
        <div>
          <h2 class="page-title">{{ detail.title }}</h2>
          <el-text type="info" size="small">
            编号 {{ detail.hazard_no }} · 上报人 {{ detail.creator_name }} · {{ formatDateTime(detail.create_time) }}
          </el-text>
        </div>
        <div class="head-actions">
          <el-button :icon="'Back'" @click="router.back()">返回列表</el-button>
          <!-- H04 派单：待处理 + 管理角色 -->
          <el-button
            v-if="canDispatch"
            type="primary"
            :icon="'User'"
            :loading="acting"
            @click="openDispatch"
          >
            派单
          </el-button>
          <!-- H05 整改：处理中 + 负责人或管理角色 -->
          <el-button
            v-if="canRectify"
            type="primary"
            :icon="'EditPen'"
            :loading="acting"
            @click="openRectify"
          >
            整改
          </el-button>
          <!-- H06 验收：待验收 + 管理角色 -->
          <el-button
            v-if="canCheck"
            type="warning"
            :icon="'Stamp'"
            :loading="acting"
            @click="openCheck"
          >
            验收
          </el-button>
          <!-- H03 一键闭环：待处理 + 管理角色 -->
          <el-button
            v-if="canClose"
            type="danger"
            :icon="'CircleCheck'"
            :loading="closing"
            @click="onClose"
          >
            闭环
          </el-button>
          <!-- O13 安全员隐患处理（模拟实现）：待处理 + 管理角色 -->
          <el-button
            v-if="canAudit"
            type="success"
            :icon="'Stamp'"
            :loading="acting"
            @click="openAudit"
          >
            处理
          </el-button>
        </div>
      </div>

      <el-row :gutter="16">
        <!-- 基本信息 + 现场图片 -->
        <el-col :xs="24" :md="14">
          <el-card shadow="never" class="block-card">
            <template #header>
              <span class="block-title">基本信息</span>
            </template>
            <el-descriptions :column="2" border class="desc-list">
              <el-descriptions-item label="隐患编号">{{ detail.hazard_no }}</el-descriptions-item>
              <el-descriptions-item label="状态">
                <el-tag :type="statusMeta(detail.status).tag">{{ statusMeta(detail.status).label }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="等级">
                <el-tag :type="levelMeta(detail.level).tag">{{ levelMeta(detail.level).label }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="类型">{{ detail.type }}</el-descriptions-item>
              <el-descriptions-item label="子类">{{ detail.subcategory || '—' }}</el-descriptions-item>
              <el-descriptions-item label="位置">{{ detail.location || '未填写' }}</el-descriptions-item>
              <el-descriptions-item label="上报人">{{ detail.creator_name }}</el-descriptions-item>
              <el-descriptions-item label="现场上报人">{{ detail.reporter_name || detail.creator_name }}</el-descriptions-item>
              <el-descriptions-item label="上报时间">{{ formatDateTime(detail.create_time) }}</el-descriptions-item>
              <el-descriptions-item label="更新时间">{{ formatDateTime(detail.update_time) }}</el-descriptions-item>
              <el-descriptions-item label="处理状态">
                <el-tag :type="auditMeta(detail.audit_status).tag" size="small">
                  {{ auditMeta(detail.audit_status).label }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="处理时间">{{ formatDateTime(detail.audit_at) }}</el-descriptions-item>
              <el-descriptions-item label="处理意见">{{ detail.audit_comment || '—' }}</el-descriptions-item>
              <el-descriptions-item label="处理期限" :span="2">{{ formatDateTime(detail.deadline) }}</el-descriptions-item>
              <el-descriptions-item label="整改措施" :span="2">
                {{ detail.rectification_measure || '未填写' }}
              </el-descriptions-item>
              <el-descriptions-item label="驳回原因" :span="2">{{ detail.reject_reason || '无' }}</el-descriptions-item>
            </el-descriptions>

            <div class="detail-section">
              <div class="block-title">隐患描述</div>
              <p class="desc-text">{{ detail.description }}</p>
            </div>

            <div class="detail-section">
              <div class="block-title">现场图片（{{ detail.images.length }}）</div>
              <div v-if="detail.images.length" class="img-list">
                <el-image
                  v-for="img in detail.images"
                  :key="img.id"
                  class="detail-img"
                  :src="img.image_url"
                  fit="contain"
                  :preview-src-list="imageUrls"
                  :initial-index="imageIndex(img.id)"
                  preview-teleported
                />
              </div>
              <el-empty v-else :image-size="60" description="无现场图片" />
            </div>
          </el-card>
        </el-col>

        <!-- 处理进度时间线 -->
        <el-col :xs="24" :md="10">
          <el-card shadow="never" class="block-card">
            <template #header>
              <span class="block-title">处理进度</span>
            </template>
            <el-timeline v-if="detail.timeline.length">
              <el-timeline-item
                v-for="log in detail.timeline"
                :key="log.id"
                :timestamp="formatDateTime(log.create_time)"
                :type="timelineType(log.operation)"
                placement="top"
              >
                <div class="log-item">
                  <div class="log-op">{{ opLabel(log.operation) }}</div>
                  <div class="log-extra">
                    <span v-if="log.operator_name">操作人：{{ log.operator_name }}</span>
                    <span v-if="log.old_status || log.new_status" class="status-flow">
                      {{ log.old_status ? statusMeta(log.old_status as HazardStatus).label : '—' }}
                      转为
                      {{ log.new_status ? statusMeta(log.new_status as HazardStatus).label : '—' }}
                    </span>
                  </div>
                  <div v-if="log.remark" class="log-remark">{{ log.remark }}</div>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else :image-size="60" description="暂无处理记录" />
          </el-card>
        </el-col>
      </el-row>

      <!-- risk_report 结构化展示（AI 识别建议 + 检测明细 + 标注图；B1：按 kept 区分展示） -->
      <el-card v-if="riskResult" shadow="never" class="block-card risk-card">
        <template #header>
          <span class="block-title">识别报告</span>
        </template>
        <AiAnalyzePanel :result="riskResult" :actionable="false" />
      </el-card>
      <el-card v-else-if="hasRiskReportField" shadow="never" class="block-card risk-card">
        <template #header>
          <span class="block-title">识别报告</span>
        </template>
        <el-empty :image-size="56" description="未保留 AI 识别结果（仅原图）" />
      </el-card>
    </template>

    <el-empty v-else-if="!error" :image-size="80" description="加载中…" />
    <el-result v-else status="error" title="加载失败" sub-title="隐患不存在或已被删除">
      <template #extra>
        <el-button type="primary" @click="router.push('/hazards')">返回列表</el-button>
      </template>
    </el-result>

    <!-- O13 隐患处理弹窗（模拟实现） -->
    <el-dialog v-model="auditVisible" :title="auditPassed ? '标记已处理' : '驳回隐患'" width="460px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="处理方式">
          <el-radio-group v-model="auditPassed">
            <el-radio :value="true">标记已处理</el-radio>
            <el-radio :value="false">驳回</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="auditPassed ? '处理意见' : '驳回意见'" :required="!auditPassed">
          <el-input
            v-model="auditComment"
            type="textarea"
            :rows="3"
            maxlength="255"
            show-word-limit
            :placeholder="auditPassed ? '选填：处理说明' : '请填写驳回原因（上报人可见）'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="auditVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="acting"
          :disabled="!auditPassed && !auditComment.trim()"
          @click="submitAudit"
        >
          确认{{ auditPassed ? '处理' : '驳回' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- H04 派单弹窗 -->
    <el-dialog v-model="dispatchVisible" title="派单处理" width="460px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="整改负责人" required>
          <el-select
            v-model="dispatchForm.handler_id"
            placeholder="选择整改负责人"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="u in employeeOptions"
              :key="u.id"
              :label="`${u.name}（${u.username}）`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="整改期限">
          <el-date-picker
            v-model="dispatchForm.deadline"
            type="datetime"
            placeholder="选填，不设期限"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dispatchVisible = false">取消</el-button>
        <el-button type="primary" :loading="acting" :disabled="!dispatchForm.handler_id" @click="onDispatch">
          确认派单
        </el-button>
      </template>
    </el-dialog>

    <!-- H05 整改弹窗 -->
    <el-dialog v-model="rectifyVisible" title="提交整改" width="520px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="整改措施" required>
          <el-input
            v-model="rectifyForm.rectification_measure"
            type="textarea"
            :rows="4"
            maxlength="2000"
            show-word-limit
            placeholder="描述已采取的整改措施"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rectifyVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="acting"
          :disabled="!rectifyForm.rectification_measure.trim()"
          @click="onRectify"
        >
          提交整改
        </el-button>
      </template>
    </el-dialog>

    <!-- H06 验收弹窗 -->
    <el-dialog v-model="checkVisible" title="验收" width="460px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="验收结论">
          <el-radio-group v-model="checkForm.passed">
            <el-radio :value="true">通过并闭环</el-radio>
            <el-radio :value="false">驳回</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="!checkForm.passed" label="驳回原因" required>
          <el-input
            v-model="checkForm.reject_reason"
            type="textarea"
            :rows="3"
            maxlength="255"
            show-word-limit
            placeholder="驳回必须填写原因"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="checkVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="acting"
          :disabled="!checkForm.passed && !checkForm.reject_reason?.trim()"
          @click="onCheck"
        >
          确认
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { checkHazard, closeHazard, dispatchHazard, getHazard, rectifyHazard } from '@/api/hazard'
import type { AnalyzeResult, HazardDetail as HazardDetailModel, HazardLevel, HazardStatus } from '@/types/models/hazard'
import { hazardLevelMeta, hazardStatusMeta } from '@/utils/constants'
import { formatDateTime } from '@/utils/format'
import { useUserStore } from '@/store/user'
import AiAnalyzePanel from '@/components/hazard/AiAnalyzePanel.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(true)
const closing = ref(false)
const acting = ref(false)
const error = ref(false)
const detail = ref<HazardDetailModel | null>(null)

/** 管理角色（SAFETY=2 / ADMIN=3） */
const isManager = computed(() => userStore.roleId === 2 || userStore.roleId === 3)

/** 操作门控（状态机 + 角色） */
const canDispatch = computed(
  () => isManager.value && detail.value?.status === 'WAIT_PROCESS',
)
const canRectify = computed(
  () => (isManager.value || detail.value?.handler_id === userStore.user?.id)
    && detail.value?.status === 'PROCESSING',
)
const canCheck = computed(
  () => isManager.value && detail.value?.status === 'WAIT_CHECK',
)
/** 闭环门控：SAFETY(2)/ADMIN(3) 且状态为 WAIT_PROCESS */
const canClose = computed(
  () => isManager.value && detail.value?.status === 'WAIT_PROCESS',
)

/** O13 隐患处理门控：SAFETY(2)/ADMIN(3) 且处理状态为 pending */
const canAudit = computed(
  () => isManager.value && detail.value?.audit_status === 'pending',
)

const AUDIT_META: Record<string, { label: string; tag: 'info' | 'success' | 'danger' }> = {
  pending: { label: '待处理', tag: 'info' },
  approved: { label: '已处理', tag: 'success' },
  rejected: { label: '已驳回', tag: 'danger' },
}
function auditMeta(v: string | undefined) {
  return AUDIT_META[v ?? 'pending'] ?? AUDIT_META.pending
}

// ---- O13 隐患处理（模拟实现） ----
const auditVisible = ref(false)
const auditPassed = ref(true)
const auditComment = ref('')

function openAudit() {
  auditPassed.value = true
  auditComment.value = ''
  auditVisible.value = true
}

async function submitAudit() {
  acting.value = true
  try {
    const { auditHazard } = await import('@/api/hazard')
    const res = await auditHazard(detail.value!.id, {
      passed: auditPassed.value,
      comment: auditComment.value.trim() || null,
    })
    ElMessage.success(res.message)
    auditVisible.value = false
    await load()
  } catch {
    // 错误已由 request 层统一提示
  } finally {
    acting.value = false
  }
}

// ---- 派单 ----
const dispatchVisible = ref(false)
const dispatchForm = ref<{ handler_id: number | null; deadline: string | null }>({ handler_id: null, deadline: null })
const employeeOptions = ref<{ id: number; name: string; username: string }[]>([])

async function loadEmployees() {
  try {
    const { listUsers } = await import('@/api/user')
    const data = await listUsers({ role_id: 1, page_size: 100 })
    employeeOptions.value = (data.items ?? []).map((u) => ({
      id: u.id, name: u.name, username: u.username,
    }))
  } catch {
    employeeOptions.value = []
  }
}

function openDispatch() {
  dispatchForm.value = { handler_id: null, deadline: null }
  dispatchVisible.value = true
  void loadEmployees()
}

async function onDispatch() {
  if (!dispatchForm.value.handler_id) return
  acting.value = true
  try {
    const res = await dispatchHazard(detail.value!.id, {
      handler_id: dispatchForm.value.handler_id,
      deadline: dispatchForm.value.deadline || null,
    })
    ElMessage.success(res.message)
    dispatchVisible.value = false
    await load()
  } catch {
    /* 全局提示 */
  } finally {
    acting.value = false
  }
}

// ---- 整改 ----
const rectifyVisible = ref(false)
const rectifyForm = ref<{ rectification_measure: string }>({ rectification_measure: '' })

function openRectify() {
  rectifyForm.value = { rectification_measure: '' }
  rectifyVisible.value = true
}

async function onRectify() {
  if (!rectifyForm.value.rectification_measure.trim()) return
  acting.value = true
  try {
    const res = await rectifyHazard(detail.value!.id, {
      rectification_measure: rectifyForm.value.rectification_measure.trim(),
    })
    ElMessage.success(res.message)
    rectifyVisible.value = false
    await load()
  } catch {
    /* 全局提示 */
  } finally {
    acting.value = false
  }
}

// ---- 验收 ----
const checkVisible = ref(false)
const checkForm = ref<{ passed: boolean; reject_reason: string | null }>({ passed: true, reject_reason: null })

function openCheck() {
  checkForm.value = { passed: true, reject_reason: null }
  checkVisible.value = true
}

async function onCheck() {
  if (!checkForm.value.passed && !checkForm.value.reject_reason?.trim()) return
  acting.value = true
  try {
    const res = await checkHazard(detail.value!.id, {
      passed: checkForm.value.passed,
      reject_reason: checkForm.value.passed ? null : checkForm.value.reject_reason?.trim() || null,
    })
    ElMessage.success(res.message)
    checkVisible.value = false
    await load()
  } catch {
    /* 全局提示 */
  } finally {
    acting.value = false
  }
}

/** 操作码 → 中文（后端存中文，兜底映射常见代码） */
const OP_LABEL: Record<string, string> = {
  SUBMIT: '提交上报',
  DISPATCH: '派单',
  RECTIFY: '整改',
  ACCEPT: '验收',
  REJECT: '驳回',
  CLOSE: '闭环确认',
}

function opLabel(op: string): string {
  return OP_LABEL[op] ?? op
}

/** 时间线节点颜色（提交绿 / 驳回红 / 其余黛青） */
function timelineType(op: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (op === 'SUBMIT' || op === '提交') return 'success'
  if (op === 'CLOSE' || op === '闭环' || op === 'REJECT' || op === '驳回') return 'danger'
  return 'primary'
}

function levelMeta(v: HazardLevel) {
  return hazardLevelMeta(v)
}

function statusMeta(v: HazardStatus) {
  return hazardStatusMeta(v)
}

const imageUrls = computed(() => detail.value?.images.map((i) => i.image_url) ?? [])

function imageIndex(id: number): number {
  return detail.value?.images.findIndex((i) => i.id === id) ?? 0
}

/** risk_report → AnalyzeResult 兼容结构（仅当含 type_suggest / detections 时展示；kept=false 视为未保留） */
const riskResult = computed<AnalyzeResult | null>(() => {
  const rr = detail.value?.risk_report
  if (!rr || typeof rr !== 'object') return null
  const r = rr as unknown as AnalyzeResult & { kept?: boolean }
  if (r.kept === false) return null // 明确不保留：仅原图
  if (r.type_suggest || (Array.isArray(r.detections) && r.detections.length)) return r
  return null
})

/** risk_report 字段存在（含 kept=false / 空结构）→ 展示「未保留 AI 识别」提示而非整卡隐藏 */
const hasRiskReportField = computed(() => {
  const rr = detail.value?.risk_report
  return !!rr && typeof rr === 'object' && Object.keys(rr as object).length > 0
})

async function load() {
  loading.value = true
  error.value = false
  try {
    detail.value = await getHazard(Number(route.params.id))
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function onClose() {
  const h = detail.value
  if (!h) return
  try {
    await ElMessageBox.confirm(
      `确认将隐患「${h.title}」直接闭环为「已闭环」吗？闭环后不可恢复。`,
      '闭环确认',
      { type: 'warning', confirmButtonText: '确认闭环', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  closing.value = true
  try {
    const res = await closeHazard(h.id)
    ElMessage.success(`${res.message}（${res.hazard_no}）`)
    await load()
  } catch {
    // 错误已由 request 层统一提示
  } finally {
    closing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.hazard-detail {
  max-width: 1240px;
  margin: 0 auto;
}

.detail-loading {
  height: 300px;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.page-title {
  margin: 0 0 4px;
  font-size: 20px;
  color: var(--el-text-color-primary, #232b2a);
}

.head-actions {
  display: flex;
  gap: 8px;
  flex: none;
}

.block-card {
  margin-bottom: 16px;
}

.block-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary, #232b2a);
}

.detail-section {
  margin-top: 16px;
}

.desc-list {
  margin-bottom: 0;
}

.desc-text {
  margin: 8px 0 0;
  font-size: 14px;
  line-height: 1.8;
  color: var(--el-text-color-regular, #4b5553);
  white-space: pre-wrap;
}

.img-list {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.detail-img {
  width: 128px;
  height: 128px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-light, #e5e1d7);
  background: #2b2f33; /* 深色底衬托 contain 图片 */
  cursor: zoom-in;
}

.log-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.log-op {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary, #232b2a);
}

.log-extra {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #707a78);
}

.status-flow {
  color: var(--el-text-color-regular, #4b5553);
}

.log-remark {
  font-size: 13px;
  color: var(--el-text-color-regular, #4b5553);
}

.risk-card :deep(.ai-analyze-panel) {
  background: var(--surface, #f8f7f3);
}
</style>
