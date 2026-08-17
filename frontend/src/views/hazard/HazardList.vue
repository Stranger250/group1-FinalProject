<!-- H02 隐患列表（P03）：筛选（状态/等级/类型/关键字/时间区间）+ 分页 + 列头排序
     （sort=create_time|level，order=asc|desc）+ 行点击进详情。筛选状态留在本组件内。 -->
<template>
  <div class="hazard-list">
    <div class="page-head">
      <h2 class="page-title">隐患列表</h2>
      <el-button type="primary" :icon="'CirclePlus'" @click="router.push('/hazards/report')">上报隐患</el-button>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form inline class="filter-form">
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 130px" @change="onSearch">
            <el-option v-for="s in HAZARD_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="等级">
          <el-select v-model="filters.level" placeholder="全部等级" clearable style="width: 130px" @change="onSearch">
            <el-option v-for="l in HAZARD_LEVELS" :key="l.value" :label="l.label" :value="l.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="filters.type" placeholder="全部类型" clearable style="width: 150px" @change="onSearch">
            <el-option v-for="t in HAZARD_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input
            v-model="filters.keyword"
            placeholder="标题 / 描述 / 位置"
            clearable
            style="width: 190px"
            @keyup.enter="onSearch"
            @clear="onSearch"
          />
        </el-form-item>
        <el-form-item label="上报时间">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            style="width: 260px"
            @change="onSearch"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="'Search'" @click="onSearch">查询</el-button>
          <el-button :icon="'RefreshLeft'" @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="items"
        class="hazard-table"
        row-key="id"
        @row-click="goDetail"
        @sort-change="onSortChange"
      >
        <el-table-column prop="hazard_no" label="隐患编号" width="180" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
        <el-table-column prop="type" label="类型" width="110" />
        <el-table-column
          prop="level"
          label="等级"
          width="100"
          sortable="custom"
          :sort-orders="['descending', 'ascending']"
        >
          <template #default="{ row }">
            <el-tag :type="levelMeta(row.level).tag">{{ levelMeta(row.level).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusMeta(row.status).tag">{{ statusMeta(row.status).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="处理状态" width="90">
          <template #default="{ row }">
            <el-tag :type="auditMeta(row.audit_status).tag" size="small">{{ auditMeta(row.audit_status).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="creator_name" label="上报人" width="110" show-overflow-tooltip />
        <el-table-column prop="reporter_name" label="现场上报人" width="120" show-overflow-tooltip />
        <el-table-column prop="image_count" label="图片" width="80" align="center">
          <template #default="{ row }">
            <span class="img-count">
              <el-icon><Picture /></el-icon>
              {{ row.image_count }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          prop="create_time"
          label="上报时间"
          width="170"
          sortable="custom"
          :sort-orders="['descending', 'ascending']"
        >
          <template #default="{ row }">{{ formatDateTime(row.create_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="goDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="load"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listHazards } from '@/api/hazard'
import type { HazardItem, HazardLevel, HazardSort, HazardStatus, SortOrder } from '@/types/models/hazard'
import { HAZARD_LEVELS, HAZARD_STATUSES, HAZARD_TYPES, hazardLevelMeta, hazardStatusMeta } from '@/utils/constants'
import { formatDateTime } from '@/utils/format'

const router = useRouter()

// ---------- 筛选条件（组件内状态） ----------
const filters = reactive<{
  status: HazardStatus | ''
  level: HazardLevel | ''
  type: string
  keyword: string
}>({ status: '', level: '', type: '', keyword: '' })

const dateRange = ref<[string, string] | null>(null)

// ---------- 分页 ----------
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

// ---------- 排序 ----------
const sortState = reactive<{ prop: HazardSort; order: SortOrder }>({ prop: 'create_time', order: 'desc' })

const loading = ref(false)
const items = ref<HazardItem[]>([])

function levelMeta(v: HazardLevel) {
  return hazardLevelMeta(v)
}

function statusMeta(v: HazardStatus) {
  return hazardStatusMeta(v)
}

/** O13 处理状态展示 */
const AUDIT_META: Record<string, { label: string; tag: 'info' | 'success' | 'danger' }> = {
  pending: { label: '待处理', tag: 'info' },
  approved: { label: '已处理', tag: 'success' },
  rejected: { label: '已驳回', tag: 'danger' },
}
function auditMeta(v: string | undefined) {
  return AUDIT_META[v ?? 'pending'] ?? AUDIT_META.pending
}

function onSearch() {
  page.value = 1
  load()
}

function onReset() {
  filters.status = ''
  filters.level = ''
  filters.type = ''
  filters.keyword = ''
  dateRange.value = null
  sortState.prop = 'create_time'
  sortState.order = 'desc'
  page.value = 1
  load()
}

function onSizeChange() {
  page.value = 1
  load()
}

function onSortChange({ prop, order }: { prop: string; order: 'ascending' | 'descending' | null }) {
  // 列头点击排序：level/create_time；取消排序时回到默认（create_time desc）
  if (!order || (prop !== 'level' && prop !== 'create_time')) {
    sortState.prop = 'create_time'
    sortState.order = 'desc'
  } else {
    sortState.prop = prop
    sortState.order = order === 'ascending' ? 'asc' : 'desc'
  }
  page.value = 1
  load()
}

async function load() {
  loading.value = true
  try {
    const [start, end] = dateRange.value ?? []
    const res = await listHazards({
      status: filters.status,
      level: filters.level,
      type: filters.type,
      keyword: filters.keyword.trim(),
      start_time: start ? `${start} 00:00:00` : '',
      end_time: end ? `${end} 23:59:59` : '',
      sort: sortState.prop,
      order: sortState.order,
      page: page.value,
      page_size: pageSize.value,
    })
    items.value = res.items
    total.value = res.total
  } catch {
    // 错误已由 request 层统一提示
  } finally {
    loading.value = false
  }
}

function goDetail(row: HazardItem) {
  router.push(`/hazards/${row.id}`)
}

onMounted(load)
</script>

<style scoped>
.hazard-list {
  max-width: 1240px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  color: #303133;
}

.filter-card {
  margin-bottom: 16px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 8px;
  margin-right: 8px;
}

.hazard-table :deep(.el-table__row) {
  cursor: pointer;
}

.img-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #606266;
  font-size: 13px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
