<template>
  <div class="picker-page">
    <div class="page-head">
      <h2 class="page-title">在线考试</h2>
      <div class="page-head-right">
        <el-link type="primary" :underline="false" @click="router.push('/exams/records')">
          <el-icon style="vertical-align: -2px"><Tickets /></el-icon>
          <span style="margin-left: 2px">我的考试记录</span>
        </el-link>
      </div>
    </div>

    <el-empty v-if="!loading && papers.length === 0" description="暂无已发布的试卷">
      <div class="empty-hint">请联系管理员发布试卷后参加考试</div>
      <el-button type="primary" :loading="loading" @click="load">刷新</el-button>
    </el-empty>

    <el-skeleton v-else-if="loading" :rows="4" animated style="margin-top: 16px" />

    <template v-else>
      <div class="paper-grid">
        <el-card v-for="p in papers" :key="p.id" class="paper-card" shadow="hover">
          <div class="paper-top">
            <div class="paper-name">{{ p.name }}</div>
            <el-tag v-if="p.ongoing_record_id" type="warning" size="small">进行中</el-tag>
          </div>
          <div class="paper-meta">
            <div class="meta-item">
              <span class="meta-label">总分</span>
              <b class="meta-value">{{ p.total_score }}</b>
            </div>
            <div class="meta-item">
              <span class="meta-label">及格线</span>
              <b class="meta-value">{{ p.pass_score }}</b>
            </div>
            <div class="meta-item">
              <span class="meta-label">时长</span>
              <b class="meta-value">{{ p.duration }} 分钟</b>
            </div>
            <div class="meta-item">
              <span class="meta-label">题数</span>
              <b class="meta-value">{{ p.question_count }} 题</b>
            </div>
          </div>
          <div class="paper-action">
            <el-button v-if="p.ongoing_record_id" type="primary" :loading="startingId === p.id" @click="onContinue(p)">
              继续考试
            </el-button>
            <el-button v-else type="primary" :loading="startingId === p.id" @click="onStart(p)">
              开始考试
            </el-button>
          </div>
        </el-card>
      </div>

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
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listPublicPapers, resumeExam, startExam } from '@/api/exam'
import type { PublicPaperItem } from '@/types/models/exam'

const router = useRouter()

const page = ref(1)
const pageSize = 20
const total = ref(0)
const papers = ref<PublicPaperItem[]>([])
const loading = ref(false)
const startingId = ref<number | null>(null)

async function load() {
  loading.value = true
  try {
    const data = await listPublicPapers(page.value, pageSize)
    papers.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function onStart(p: PublicPaperItem) {
  startingId.value = p.id
  try {
    const sheet = await startExam({ paper_id: p.id })
    if (sheet.state === 'SUBMITTED') {
      ElMessage.info('该试卷已存在交卷记录，正在查看成绩单')
      router.replace(`/exams/${sheet.record_id}/result`)
    } else {
      router.replace(`/exams/${sheet.record_id}`)
    }
  } catch {
    // 错误已由请求层统一提示（404 未发布 / 409 冲突等）
  } finally {
    startingId.value = null
  }
}

async function onContinue(p: PublicPaperItem) {
  if (!p.ongoing_record_id) return
  startingId.value = p.id
  try {
    const data = await resumeExam(p.ongoing_record_id)
    if (data.state === 'SUBMITTED') {
      ElMessage.info('该考试已交卷，正在查看成绩单')
      router.replace(`/exams/${p.ongoing_record_id}/result`)
    } else {
      router.replace(`/exams/${p.ongoing_record_id}`)
    }
  } catch {
    // 错误已由请求层统一提示
  } finally {
    startingId.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.picker-page {
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

.empty-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 12px;
}

.paper-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.paper-card {
  border-radius: 6px;
}

.paper-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.paper-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.4;
  margin-bottom: 14px;
}

.paper-meta {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 8px;
  padding: 12px;
  border-radius: 8px;
  background: var(--el-bg-color-page);
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.meta-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.meta-value {
  font-size: 15px;
  color: var(--el-text-color-primary);
}

.paper-action {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.pager {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
