<template>
  <div class="page-container">
    <el-card v-loading="loading" shadow="never" class="stats-card">
      <template #header>
        <div class="card-title">AI 出题统计</div>
      </template>

      <el-row :gutter="16">
        <el-col :span="4">
          <div class="stat-box">
            <div class="stat-value">{{ stats?.total_ai ?? 0 }}</div>
            <div class="stat-label">生成题目总数</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="stat-box stat-pending">
            <div class="stat-value">{{ stats?.total_pending ?? 0 }}</div>
            <div class="stat-label">待审核</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="stat-box stat-approved">
            <div class="stat-value">{{ stats?.total_approved ?? 0 }}</div>
            <div class="stat-label">已通过</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="stat-box stat-rejected">
            <div class="stat-value">{{ stats?.total_rejected ?? 0 }}</div>
            <div class="stat-label">已驳回</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="stat-box">
            <div class="stat-value">{{ stats?.total_rewritten ?? 0 }}</div>
            <div class="stat-label">重写数</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="stat-box stat-pass">
            <div class="stat-value">{{ passPercentText }}</div>
            <div class="stat-label">整体通过率</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-title">
          批次明细
          <span class="card-sub">通过率 ≥80% 为达标（success 色）</span>
        </div>
      </template>
      <el-table :data="stats?.batches ?? []" stripe>
        <el-table-column prop="batch_id" label="批次号" min-width="220" show-overflow-tooltip />
        <el-table-column prop="total" label="总题数" width="80" />
        <el-table-column prop="pending" label="待审" width="80" />
        <el-table-column prop="approved" label="通过" width="80" />
        <el-table-column prop="rejected" label="驳回" width="80" />
        <el-table-column label="通过率" width="190">
          <template #default="{ row }">
            <el-progress :percentage="passPercent(row as BatchItem)" :status="passStatus(row as BatchItem)" :stroke-width="14" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="goDetail((row as BatchItem).batch_id)">
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !stats?.batches?.length" description="暂无出题批次" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getGenStats } from '@/api/exam'
import type { BatchItem, GenStats } from '@/types/models/exam'

const router = useRouter()
const loading = ref(false)
const stats = ref<GenStats | null>(null)

const passPercentText = computed(() => (stats.value ? `${Math.round((stats.value.pass_rate ?? 0) * 100)}%` : '-'))

async function load(): Promise<void> {
  loading.value = true
  try {
    stats.value = await getGenStats()
  } finally {
    loading.value = false
  }
}

function passPercent(b: BatchItem): number {
  return Math.round((b.pass_rate ?? 0) * 100)
}

function passStatus(b: BatchItem): 'success' | 'warning' {
  return (b.pass_rate ?? 0) >= 0.8 ? 'success' : 'warning'
}

function goDetail(batchId: string): void {
  router.push(`/exam/ai/batches/${batchId}`)
}

void load()
</script>

<style scoped>
.stats-card {
  margin-bottom: 12px;
}
.card-title {
  font-size: 16px;
  font-weight: 600;
}
.card-sub {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.stat-box {
  background: var(--surface);
  border-radius: 6px;
  padding: 16px;
  text-align: center;
}
.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  line-height: 1.2;
}
.stat-label {
  margin-top: 6px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.stat-pending .stat-value {
  color: var(--el-color-warning);
}
.stat-approved .stat-value {
  color: var(--el-color-success);
}
.stat-rejected .stat-value {
  color: var(--el-color-danger);
}
.stat-pass .stat-value {
  color: var(--el-color-primary);
}
</style>
