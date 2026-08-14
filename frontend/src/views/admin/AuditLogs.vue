<template>
  <div class="page-container">
    <el-card shadow="never" class="filter-card">
      <div class="toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="操作人 / 详情关键字"
          clearable
          style="width: 220px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-select v-model="query.action" placeholder="动作" clearable style="width: 180px" @change="handleSearch">
          <el-option v-for="(label, key) in AUDIT_ACTION_LABELS" :key="key" :label="label" :value="key" />
        </el-select>
        <el-date-picker
          v-model="timeRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          style="width: 360px"
          @change="handleSearch"
        />
        <el-button type="primary" :icon="'Search'" @click="handleSearch">查询</el-button>
        <el-button :icon="'Refresh'" @click="handleReset">重置</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="pageData?.items ?? []" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="时间" width="165">
          <template #default="{ row }">{{ formatDateTime((row as AuditLogItem).create_time) }}</template>
        </el-table-column>
        <el-table-column label="操作人" width="140">
          <template #default="{ row }">
            <span>{{ (row as AuditLogItem).username || '—' }}</span>
            <span class="uid">#{{ (row as AuditLogItem).user_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="动作" width="160">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ auditActionLabel((row as AuditLogItem).action) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="对象" width="160">
          <template #default="{ row }">
            <span v-if="(row as AuditLogItem).target_type">
              {{ (row as AuditLogItem).target_type }}#{{ (row as AuditLogItem).target_id }}
            </span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" min-width="240" show-overflow-tooltip />
        <el-table-column prop="ip" label="IP" width="130">
          <template #default="{ row }">{{ (row as AuditLogItem).ip || '—' }}</template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="pageData?.total ?? 0"
          layout="total, prev, pager, next, sizes"
          :page-sizes="[10, 20, 50]"
          @change="load"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { AUDIT_ACTION_LABELS, auditActionLabel, listAuditLogs, type AuditLogItem } from '@/api/logs'
import type { PageResult } from '@/types/api'
import { formatDateTime } from '@/utils/format'

const loading = ref(false)
const pageData = ref<PageResult<AuditLogItem> | null>(null)
const timeRange = ref<[string, string] | null>(null)

const query = reactive<{ action: string; keyword: string; start_time?: string; end_time?: string; page: number; page_size: number }>({
  action: '',
  keyword: '',
  page: 1,
  page_size: 20,
})

async function load(): Promise<void> {
  loading.value = true
  try {
    pageData.value = await listAuditLogs({
      action: query.action || undefined,
      keyword: query.keyword || undefined,
      start_time: timeRange.value?.[0],
      end_time: timeRange.value?.[1],
      page: query.page,
      page_size: query.page_size,
    })
  } catch {
    /* 全局提示 */
  } finally {
    loading.value = false
  }
}

function handleSearch(): void {
  query.page = 1
  void load()
}

function handleReset(): void {
  query.action = ''
  query.keyword = ''
  timeRange.value = null
  query.page = 1
  void load()
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.uid {
  margin-left: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
