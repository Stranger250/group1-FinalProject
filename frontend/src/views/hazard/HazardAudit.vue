<!-- O13 安全员隐患处理页（模拟实现）：列表（待处理/已处理筛选）+ 详情 + 标记已处理/驳回。
     仅 SAFETY/ADMIN 可见（路由 meta.roles）；处理结果落库（audit_status/audit_by/audit_at/audit_comment）。 -->
<template>
  <div class="hazard-audit">
    <div class="page-head">
      <h2 class="page-title">隐患处理</h2>
      <el-text type="info" size="small">安全员对上报隐患进行模拟处理（已处理/驳回 + 意见），处理结果对上报人可见</el-text>
    </div>

    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group v-model="query.audit_status" @change="load(1)">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="pending">待处理</el-radio-button>
          <el-radio-button value="approved">已处理</el-radio-button>
          <el-radio-button value="rejected">已驳回</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="query.keyword"
          placeholder="搜索标题/描述/位置"
          clearable
          style="width: 240px"
          @keyup.enter="load(1)"
          @clear="load(1)"
        >
          <template #append>
            <el-button :icon="'Search'" @click="load(1)" />
          </template>
        </el-input>
      </div>

      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="hazard_no" label="隐患编号" width="150" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="reporter_name" label="现场上报人" width="110" />
        <el-table-column label="等级" width="90">
          <template #default="{ row }">
            <el-tag :type="levelTag(row.level)" size="small">{{ levelLabel(row.level) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="110" />
        <el-table-column label="处理状态" width="100">
          <template #default="{ row }">
            <el-tag :type="auditTag(row.audit_status)" size="small">{{ auditLabel(row.audit_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="openDetail(row.id)">查看</el-button>
            <el-button
              v-if="row.audit_status === 'pending'"
              size="small"
              type="success"
              plain
              @click="openProcess(row, true)"
            >
              标记已处理
            </el-button>
            <el-button
              v-if="row.audit_status === 'pending'"
              size="small"
              type="danger"
              plain
              @click="openProcess(row, false)"
            >
              驳回
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="query.page"
        :page-size="query.page_size"
        :total="total"
        layout="total, prev, pager, next"
        class="pager"
        @current-change="load"
      />
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawerVisible" :title="detail?.hazard_no ?? '隐患详情'" size="520px">
      <template v-if="detail">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="标题">{{ detail.title }}</el-descriptions-item>
          <el-descriptions-item label="描述">{{ detail.description }}</el-descriptions-item>
          <el-descriptions-item label="位置">{{ detail.location }}</el-descriptions-item>
          <el-descriptions-item label="等级">{{ levelLabel(detail.level) }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ detail.type }}</el-descriptions-item>
          <el-descriptions-item label="现场上报人">{{ detail.reporter_name || detail.creator_name }}</el-descriptions-item>
          <el-descriptions-item label="上报时间">{{ detail.create_time }}</el-descriptions-item>
          <el-descriptions-item label="处理状态">
            <el-tag :type="auditTag(detail.audit_status)" size="small">{{ auditLabel(detail.audit_status) }}</el-tag>
          </el-descriptions-item>
          <template v-if="detail.audit_at">
            <el-descriptions-item label="处理人">{{ detail.audit_by ? `#${detail.audit_by}` : '—' }}</el-descriptions-item>
            <el-descriptions-item label="处理时间">{{ detail.audit_at }}</el-descriptions-item>
            <el-descriptions-item label="处理意见">{{ detail.audit_comment || '—' }}</el-descriptions-item>
          </template>
        </el-descriptions>
        <div v-if="detail.images.length" class="img-list">
          <el-image
            v-for="img in detail.images"
            :key="img.id"
            :src="img.image_url"
            :preview-src-list="detail.images.map((i) => i.image_url)"
            fit="cover"
            class="img-item"
          />
        </div>
        <div class="drawer-actions">
          <el-button
            v-if="detail.audit_status === 'pending'"
            type="success"
            :loading="acting"
            @click="openProcess(detail, true)"
          >
            标记已处理
          </el-button>
          <el-button
            v-if="detail.audit_status === 'pending'"
            type="danger"
            :loading="acting"
            @click="openProcess(detail, false)"
          >
            驳回
          </el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 处理弹窗 -->
    <el-dialog v-model="processVisible" :title="processPassed ? '标记已处理' : '驳回隐患'" width="460px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="隐患编号">
          <el-text>{{ processTarget?.hazard_no }}</el-text>
        </el-form-item>
        <el-form-item v-if="!processPassed" label="驳回意见" required>
          <el-input
            v-model="processComment"
            type="textarea"
            :rows="3"
            maxlength="255"
            show-word-limit
            placeholder="请填写驳回原因（上报人可见）"
          />
        </el-form-item>
        <el-form-item v-else label="处理意见">
          <el-input
            v-model="processComment"
            type="textarea"
            :rows="3"
            maxlength="255"
            show-word-limit
            placeholder="选填：处理说明"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="processVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="acting"
          :disabled="!processPassed && !processComment.trim()"
          @click="submitProcess"
        >
          确认{{ processPassed ? '处理' : '驳回' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { auditHazard, getHazard, listHazards } from '@/api/hazard'
import type { HazardAuditStatus, HazardDetail, HazardItem, HazardLevel } from '@/types/models/hazard'

const loading = ref(false)
const acting = ref(false)
const items = ref<HazardItem[]>([])
const total = ref(0)
const query = reactive({ audit_status: '' as '' | HazardAuditStatus, keyword: '', page: 1, page_size: 10 })

const drawerVisible = ref(false)
const detail = ref<HazardDetail | null>(null)
const processVisible = ref(false)
const processPassed = ref(true)
const processComment = ref('')
const processTarget = ref<HazardDetail | null>(null)

const LEVEL_META: Record<HazardLevel, { label: string; tag: 'danger' | 'warning' | 'primary' | 'info' }> = {
  CRITICAL: { label: '重大', tag: 'danger' },
  MAJOR: { label: '较大', tag: 'warning' },
  GENERAL: { label: '一般', tag: 'primary' },
  MINOR: { label: '轻微', tag: 'info' },
}

const AUDIT_META: Record<HazardAuditStatus, { label: string; tag: 'info' | 'success' | 'danger' }> = {
  pending: { label: '待处理', tag: 'info' },
  approved: { label: '已处理', tag: 'success' },
  rejected: { label: '已驳回', tag: 'danger' },
}

function levelLabel(v: HazardLevel) {
  return LEVEL_META[v]?.label ?? v
}
function levelTag(v: HazardLevel) {
  return LEVEL_META[v]?.tag ?? 'info'
}
function auditLabel(v: HazardAuditStatus) {
  return AUDIT_META[v]?.label ?? v
}
function auditTag(v: HazardAuditStatus) {
  return AUDIT_META[v]?.tag ?? 'info'
}

async function load(page = query.page) {
  query.page = page
  loading.value = true
  try {
    const res = await listHazards({
      keyword: query.keyword || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    const all = res.items
    // 安全员视角可看全部；前端按处理状态过滤（后端不提供该筛选参数）
    items.value = query.audit_status ? all.filter((i) => i.audit_status === query.audit_status) : all
    total.value = query.audit_status ? items.value.length : res.total
  } finally {
    loading.value = false
  }
}

async function openDetail(id: number) {
  drawerVisible.value = true
  try {
    detail.value = await getHazard(id)
  } catch {
    drawerVisible.value = false
  }
}

function openProcess(target: HazardDetail | HazardItem, passed: boolean) {
  processTarget.value = { ...(target as HazardDetail) }
  processPassed.value = passed
  processComment.value = ''
  processVisible.value = true
}

async function submitProcess() {
  if (!processTarget.value) return
  acting.value = true
  try {
    const res = await auditHazard(processTarget.value.id, {
      passed: processPassed.value,
      comment: processComment.value.trim() || null,
    })
    ElMessage.success(res.message)
    processVisible.value = false
    await load()
    if (drawerVisible.value && detail.value) {
      detail.value = await getHazard(detail.value.id)
    }
  } catch {
    // 错误已由 request 层统一提示
  } finally {
    acting.value = false
  }
}

onMounted(() => load(1))
</script>

<style scoped>
.hazard-audit {
  max-width: 1100px;
  margin: 0 auto;
}
.page-head {
  margin-bottom: 16px;
}
.page-title {
  margin: 0 0 4px;
  font-size: 20px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.pager {
  margin-top: 14px;
  justify-content: flex-end;
}
.img-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.img-item {
  width: 120px;
  height: 90px;
  border-radius: 6px;
}
.drawer-actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
}
</style>
