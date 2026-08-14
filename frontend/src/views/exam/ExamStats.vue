<template>
  <div class="page-container">
    <el-card shadow="never" class="filter-card">
      <div class="toolbar">
        <h3 class="block-title">考试统计</h3>
        <el-switch
          v-if="isAdmin"
          v-model="allScope"
          active-text="全站统计"
          inactive-text="我的统计"
          @change="load"
        />
        <el-button :icon="'Refresh'" @click="load">刷新</el-button>
      </div>
    </el-card>

    <div v-loading="loading">
      <!-- 总览卡片 -->
      <el-row :gutter="16" class="stat-row">
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-num">{{ stats?.total_exams ?? 0 }}</div>
            <div class="stat-label">考试场次</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-num" :class="(stats?.pass_rate ?? 0) >= 0.6 ? 'pass' : 'warn'">
              {{ percent(stats?.pass_rate ?? 0) }}
            </div>
            <div class="stat-label">通过率</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-num">{{ stats?.passed_exams ?? 0 }}</div>
            <div class="stat-label">合格场次</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-num">{{ stats?.avg_score ?? 0 }}</div>
            <div class="stat-label">平均分</div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <!-- 知识点掌握度 -->
        <el-col :span="12">
          <el-card shadow="never" class="block-card">
            <template #header><span class="block-title">知识点掌握度</span></template>
            <el-empty v-if="!stats?.knowledge_mastery?.length" :image-size="60" description="暂无数据" />
            <div v-for="k in stats?.knowledge_mastery ?? []" :key="k.knowledge_point" class="mastery-row">
              <span class="mastery-name">{{ k.knowledge_point }}</span>
              <el-progress
                :percentage="Math.round(k.mastery * 100)"
                :status="k.mastery >= 0.8 ? 'success' : k.mastery >= 0.6 ? '' : 'exception'"
                style="flex: 1"
              />
              <span class="mastery-count">{{ k.correct }}/{{ k.total }}</span>
            </div>
          </el-card>
        </el-col>

        <!-- 错题排行 -->
        <el-col :span="12">
          <el-card shadow="never" class="block-card">
            <template #header><span class="block-title">错题排行 TOP</span></template>
            <el-empty v-if="!stats?.wrong_top?.length" :image-size="60" description="暂无错题数据" />
            <div v-for="(w, i) in stats?.wrong_top ?? []" :key="w.question_id" class="wrong-row">
              <span class="wrong-rank">{{ i + 1 }}</span>
              <span class="wrong-id">题 #{{ w.question_id }}</span>
              <el-progress :percentage="Math.min(100, w.wrong_count * 10)" style="flex: 1" />
              <span class="wrong-count">{{ w.wrong_count }} 次</span>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getExamStats } from '@/api/exam'
import { useUserStore } from '@/store/user'
import type { ExamStats } from '@/types/models/exam'
import { percent } from '@/utils/format'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.roleId === 3)
const allScope = ref(false)
const loading = ref(false)
const stats = ref<ExamStats | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    stats.value = await getExamStats(allScope.value ? 1 : 0)
  } catch {
    /* 全局提示 */
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.block-title {
  margin: 0;
  font-size: 15px;
}
.stat-row {
  margin-bottom: 16px;
}
.stat-card {
  text-align: center;
  padding: 4px 0;
}
.stat-num {
  font-size: 30px;
  font-weight: 700;
  color: var(--el-color-primary);
}
.stat-num.pass {
  color: var(--el-color-success);
}
.stat-num.warn {
  color: var(--el-color-warning);
}
.stat-label {
  margin-top: 4px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.mastery-row,
.wrong-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
}
.mastery-name {
  width: 160px;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mastery-count,
.wrong-count {
  width: 56px;
  text-align: right;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.wrong-rank {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  background: var(--brand-soft);
  color: var(--el-color-primary);
  font-weight: 600;
  text-align: center;
  line-height: 22px;
  font-size: 13px;
}
.wrong-id {
  width: 90px;
  font-size: 13px;
}
</style>
