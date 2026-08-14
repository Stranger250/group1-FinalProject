<template>
  <div class="records-page">
    <div class="page-head">
      <h2 class="page-title">我的考试记录</h2>
      <el-button @click="router.push('/exams')">返回选卷</el-button>
    </div>

    <el-card shadow="never" class="table-card">
      <el-table :data="records" v-loading="loading" stripe>
        <el-table-column prop="paper_name" label="试卷名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.state === 'ONGOING' ? 'warning' : 'info'">
              {{ row.state === 'ONGOING' ? '进行中' : '已交卷' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="得分" width="90" align="center">
          <template #default="{ row }">
            {{ row.state === 'SUBMITTED' ? row.score : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="是否合格" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.state === 'SUBMITTED'" :type="row.passed ? 'success' : 'danger'" size="small">
              {{ row.passed ? '合格' : '不合格' }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="切屏次数" width="90" align="center">
          <template #default="{ row }">{{ row.cheat_count }}</template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.submitted_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="center" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.state === 'ONGOING'" type="primary" link @click="router.push(`/exams/${row.record_id}`)">
              继续考试
            </el-button>
            <el-button v-else type="primary" link @click="router.push(`/exams/${row.record_id}/result`)">
              查看成绩单
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next, total"
          background
          @current-change="load"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listMyExamRecords } from '@/api/exam'
import type { ExamRecordItem } from '@/types/models/exam'
import { formatDateTime } from '@/utils/format'

const router = useRouter()

const page = ref(1)
const pageSize = 20
const total = ref(0)
const records = ref<ExamRecordItem[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await listMyExamRecords(page.value, pageSize)
    records.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.records-page {
  padding: 4px;
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
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.table-card {
  border-radius: 6px;
}

.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
