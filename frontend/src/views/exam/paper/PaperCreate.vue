<template>
  <div class="page-container">
    <el-card shadow="never" class="config-card">
      <template #header>
        <div class="card-title">
          {{ isAuto ? '自动组卷' : '手动组卷' }}
          <span class="card-sub">{{ isAuto ? '从已审核题库按规则抽题，不生成新题' : '从题库勾选已审核题目组卷' }}</span>
        </div>
      </template>
      <el-form ref="baseFormRef" :model="base" :rules="baseRules" label-width="92px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="试卷名称" prop="name">
              <el-input v-model="base.name" maxlength="128" show-word-limit placeholder="请输入试卷名称" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="考试时长" prop="duration">
              <el-select v-model="base.duration" style="width: 100%">
                <el-option v-for="d in PAPER_DURATIONS" :key="d.value" :label="d.label" :value="d.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="6">
            <el-form-item label="总分" prop="total_score">
              <el-input-number v-model="base.total_score" :min="10" :max="500" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="及格线" prop="pass_score">
              <el-input-number v-model="base.pass_score" :min="1" :max="500" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="知识点">
              <el-select
                v-if="isAuto"
                v-model="knowledgePoints"
                multiple
                filterable
                allow-create
                default-first-option
                placeholder="选填，回车创建知识点"
                style="width: 100%"
              >
                <el-option v-for="kp in knowledgePoints" :key="kp" :label="kp" :value="kp" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 手动组卷：选题区 + 已选列表 -->
    <template v-if="!isAuto">
      <el-card shadow="never" class="picker-card">
        <template #header>
          <div class="card-title">从题库选题 <span class="card-sub">仅展示已通过（APPROVED）题目</span></div>
        </template>
        <div class="picker-filter">
          <el-select v-model="picker.type" placeholder="题型" clearable style="width: 130px">
            <el-option v-for="t in QUESTION_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
          <el-select v-model="picker.difficulty" placeholder="难度" clearable style="width: 120px">
            <el-option v-for="d in DIFFICULTIES" :key="d.value" :label="d.label" :value="d.value" />
          </el-select>
          <el-input
            v-model="picker.keyword"
            placeholder="题干关键词"
            clearable
            style="width: 200px"
            @keyup.enter="pickerSearch"
            @clear="pickerSearch"
          />
          <el-button type="primary" :icon="'Search'" @click="pickerSearch">搜索</el-button>
          <el-button :icon="'Refresh'" @click="pickerReset">重置</el-button>
        </div>

        <el-table v-loading="pickerLoading" :data="pickerData?.items ?? []" stripe size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column label="题型" width="80">
            <template #default="{ row }">
              {{ questionTypeLabel((row as Question).type) }}
            </template>
          </el-table-column>
          <el-table-column prop="content" label="题干" min-width="300" show-overflow-tooltip />
          <el-table-column label="难度" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="difficultyMeta((row as Question).difficulty).tag">
                {{ difficultyMeta((row as Question).difficulty).label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                size="small"
                :disabled="isSelected((row as Question).id)"
                @click="addToSelected(row as Question)"
              >
                {{ isSelected((row as Question).id) ? '已添加' : '添加' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrap">
          <el-pagination
            v-model:current-page="picker.page"
            v-model:page-size="picker.page_size"
            :total="pickerData?.total ?? 0"
            :page-sizes="[10, 20, 50]"
            layout="total, prev, pager, next"
            background
            small
            @current-change="loadPicker"
            @size-change="pickerSizeChange"
          />
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-title">
            已选题目（{{ selected.length }}）
            <el-radio-group v-model="scoreStrategy" class="ml8" size="small">
              <el-radio value="average">总分均分</el-radio>
              <el-radio value="assign">全部指定分值</el-radio>
            </el-radio-group>
          </div>
        </template>

        <el-table :data="selected" stripe size="small">
          <el-table-column label="序号" width="60">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column label="题型" width="80">
            <template #default="{ row }">{{ questionTypeLabel((row as SelectedQuestion).type) }}</template>
          </el-table-column>
          <el-table-column prop="content" label="题干" min-width="280" show-overflow-tooltip />
          <el-table-column label="分值" width="140">
            <template #default="{ row }">
              <el-input-number
                v-if="scoreStrategy === 'assign'"
                v-model="(row as SelectedQuestion).score"
                :min="1"
                :max="500"
                size="small"
                :controls="false"
                style="width: 90px"
              />
              <span v-else>均分</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="removeSelected($index)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!selected.length" description="尚未选题" :image-size="60" />
      </el-card>
    </template>

    <!-- 自动组卷：抽题规则 -->
    <el-card v-else shadow="never">
      <template #header>
        <div class="card-title">抽题规则 <span class="card-sub">至少一条，难度留空 = 全部难度</span></div>
      </template>
      <el-alert
        class="auto-tip"
        type="info"
        :closable="false"
        show-icon
        title="自动组卷不会生成新题，仅从题库中已审核（APPROVED）的题目按规则抽取"
      >
        <template #default>
          需要按知识点/题型生成全新题目？请先
          <el-link type="primary" @click="goAiGenerate">去 AI 出题</el-link>
          生成并审核通过后再回来组卷。
        </template>
      </el-alert>
      <el-table :data="rules" stripe size="small">
        <el-table-column label="题型" min-width="140">
          <template #default="{ row }">
            <el-select v-model="(row as AutoRule).type" placeholder="题型" style="width: 120px">
              <el-option v-for="t in QUESTION_TYPES" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="难度" min-width="140">
          <template #default="{ row }">
            <el-select v-model="(row as AutoRule).difficulty" placeholder="全部难度" clearable style="width: 120px">
              <el-option v-for="d in DIFFICULTIES" :key="d.value" :label="d.label" :value="d.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="数量" min-width="140">
          <template #default="{ row }">
            <el-input-number v-model="(row as AutoRule).count" :min="1" :max="100" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" :disabled="rules.length <= 1" @click="removeRule($index)">
              移除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button size="small" class="mt12" :icon="'Plus'" @click="addRule">添加规则</el-button>
    </el-card>

    <div class="submit-bar">
      <el-button size="large" @click="router.back()">取消</el-button>
      <el-button type="primary" size="large" :loading="submitting" @click="handleSubmit">
        {{ isAuto ? '自动组卷' : '生成试卷' }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { DIFFICULTIES, PAPER_DURATIONS, QUESTION_TYPES, difficultyMeta, questionTypeLabel } from '@/utils/constants'
import { createPaperAuto, createPaperManual, listQuestions } from '@/api/exam'
import type { PageResult } from '@/types/api'
import type { Question, QuestionDifficulty, QuestionType } from '@/types/models/exam'

const route = useRoute()
const router = useRouter()

const isAuto = computed(() => route.query.mode === 'auto')

/** 自动组卷 → AI 出题（互跳入口：出题产出题库，组卷消费已审核题库） */
function goAiGenerate(): void {
  router.push('/exam/ai/generate')
}

type PaperDuration = 30 | 60 | 90

const baseFormRef = ref<FormInstance>()
const base = reactive<{ name: string; duration: PaperDuration; pass_score: number; total_score: number }>({
  name: '',
  duration: 60,
  pass_score: 60,
  total_score: 100,
})

const baseRules = reactive<FormRules>({
  name: [{ required: true, message: '请输入试卷名称', trigger: 'blur' }],
  duration: [{ required: true, message: '请选择考试时长', trigger: 'change' }],
  total_score: [{ required: true, message: '请输入总分', trigger: 'blur' }],
  pass_score: [{ required: true, message: '请输入及格线', trigger: 'blur' }],
})

// ---------- 手动组卷 ----------
interface SelectedQuestion {
  id: number
  content: string
  type: QuestionType
  difficulty: QuestionDifficulty
  score: number | null
}

const selected = ref<SelectedQuestion[]>([])
const scoreStrategy = ref<'average' | 'assign'>('average')

const picker = reactive({
  type: '' as '' | QuestionType,
  difficulty: '' as '' | QuestionDifficulty,
  keyword: '',
  page: 1,
  page_size: 10,
})
const pickerLoading = ref(false)
const pickerData = ref<PageResult<Question> | null>(null)

async function loadPicker(): Promise<void> {
  pickerLoading.value = true
  try {
    pickerData.value = await listQuestions({
      status: 'APPROVED',
      type: picker.type,
      difficulty: picker.difficulty,
      keyword: picker.keyword || undefined,
      page: picker.page,
      page_size: picker.page_size,
    })
  } finally {
    pickerLoading.value = false
  }
}

function pickerSearch(): void {
  picker.page = 1
  void loadPicker()
}

function pickerReset(): void {
  picker.type = ''
  picker.difficulty = ''
  picker.keyword = ''
  picker.page = 1
  void loadPicker()
}

function pickerSizeChange(): void {
  picker.page = 1
  void loadPicker()
}

function isSelected(id: number): boolean {
  return selected.value.some((q) => q.id === id)
}

function addToSelected(q: Question): void {
  if (isSelected(q.id)) return
  const nextLen = selected.value.length + 1
  const score =
    scoreStrategy.value === 'assign' ? Math.round(base.total_score / nextLen) : null
  selected.value.push({
    id: q.id,
    content: q.content,
    type: q.type,
    difficulty: q.difficulty,
    score,
  })
}

function removeSelected(index: number): void {
  selected.value.splice(index, 1)
}

// ---------- AI 智能组卷 ----------
interface AutoRule {
  type: QuestionType
  difficulty: QuestionDifficulty | ''
  count: number
}
const rules = ref<AutoRule[]>([{ type: 'SINGLE', difficulty: 'MEDIUM', count: 5 }])
const knowledgePoints = ref<string[]>([])

function addRule(): void {
  rules.value.push({ type: 'SINGLE', difficulty: '' as QuestionDifficulty | '', count: 5 })
}

function removeRule(index: number): void {
  if (rules.value.length <= 1) return
  rules.value.splice(index, 1)
}

// ---------- 提交 ----------
const submitting = ref(false)

function validateBase(): Promise<boolean> {
  return baseFormRef.value?.validate().catch(() => false) ?? Promise.resolve(false)
}

async function handleSubmit(): Promise<void> {
  const ok = await validateBase()
  if (!ok) return
  if (base.pass_score > base.total_score) {
    ElMessage.warning('及格线不能高于总分')
    return
  }
  if (isAuto.value) {
    await submitAuto()
  } else {
    await submitManual()
  }
}

async function submitManual(): Promise<void> {
  if (!selected.value.length) {
    ElMessage.warning('请至少选择一道题目')
    return
  }
  if (scoreStrategy.value === 'assign') {
    if (selected.value.some((q) => q.score == null)) {
      ElMessage.warning('请为每道题指定分值')
      return
    }
    const sum = selected.value.reduce((acc, q) => acc + (q.score ?? 0), 0)
    if (sum !== base.total_score) {
      ElMessage.warning(`题目分值之和 ${sum} 与总分 ${base.total_score} 不一致`)
      return
    }
  }
  submitting.value = true
  try {
    const res = await createPaperManual({
      name: base.name.trim(),
      duration: base.duration,
      pass_score: base.pass_score,
      total_score: base.total_score,
      questions: selected.value.map((q) => ({
        question_id: q.id,
        score: scoreStrategy.value === 'assign' ? q.score : null,
      })),
    })
    ElMessage.success('试卷已创建')
    router.push(`/exam/papers/${res.id}`)
  } catch {
    // 后端 message 已提示
  } finally {
    submitting.value = false
  }
}

async function submitAuto(): Promise<void> {
  if (!rules.value.length) {
    ElMessage.warning('请至少添加一条抽题规则')
    return
  }
  if (rules.value.some((r) => r.count < 1)) {
    ElMessage.warning('每条规则的题目数量不能少于 1')
    return
  }
  submitting.value = true
  try {
    const res = await createPaperAuto({
      name: base.name.trim(),
      duration: base.duration,
      pass_score: base.pass_score,
      total_score: base.total_score,
      rules: rules.value.map((r) => ({
        type: r.type,
        difficulty: r.difficulty || null,
        count: r.count,
      })),
      knowledge_points: knowledgePoints.value.length ? [...knowledgePoints.value] : null,
    })
    const warnings = res.warnings
    if (warnings && warnings.length) {
      await ElMessageBox.alert(warnings.join('\n'), '部分题型题目不足，试卷已按可用题目生成', {
        type: 'warning',
        confirmButtonText: '查看试卷',
      })
    } else {
      ElMessage.success('试卷已创建')
    }
    router.push(`/exam/papers/${res.id}`)
  } catch {
    // 400/502 message 已提示，停留表单
  } finally {
    submitting.value = false
  }
}

if (!isAuto.value) {
  void loadPicker()
}
// 切换组卷方式时按需加载选题数据（同路由 query 切换的场景兜底）
watch(isAuto, (auto) => {
  if (!auto) void loadPicker()
})
</script>

<style scoped>
.config-card {
  margin-bottom: 12px;
}
.picker-card {
  margin-bottom: 12px;
}
.auto-tip {
  margin-bottom: 12px;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: center;
}
.card-sub {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.ml8 {
  margin-left: 12px;
}
.mt12 {
  margin-top: 12px;
}
.picker-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}
.pagination-wrap {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.submit-bar {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
