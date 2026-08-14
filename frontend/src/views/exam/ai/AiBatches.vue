<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-title">
          AI 出题批次
          <span class="card-sub">按批次审核题目，通过率 ≥80% 视为达标（success 色）</span>
        </div>
      </template>

      <el-table v-loading="loading" :data="batches" stripe>
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
            <el-button link type="primary" size="small" @click="goDetail((row as BatchItem).batch_id)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && !batches.length" description="暂无出题批次，可先到「AI 出题」生成" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { listBatches } from '@/api/exam'
import type { BatchItem } from '@/types/models/exam'

const router = useRouter()
const loading = ref(false)
const batches = ref<BatchItem[]>([])

async function load(): Promise<void> {
  loading.value = true
  try {
    batches.value = await listBatches()
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
</style>
