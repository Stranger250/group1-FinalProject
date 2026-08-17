<!-- O8 用户端考试工坊：① 我的试卷（组卷/发布考试/撤销/导出Word/删除）② 分享给我的（作答/收藏）③ 题目库（查询+添加，需管理员审核） -->
<template>
  <div class="exam-workshop">
    <div class="page-head">
      <h2 class="page-title">考试工坊</h2>
      <el-text type="info" size="small">生成试卷 → 发布考试给指定用户 → 自动收集作答统计；他人发布的考试可直接作答或收藏</el-text>
    </div>

    <el-tabs v-model="tab" class="ws-tabs">
      <!-- ============ 我的试卷 ============ -->
      <el-tab-pane label="我的试卷" name="mine">
        <div class="toolbar">
          <el-button type="primary" :icon="'CirclePlus'" @click="openCreate">组卷</el-button>
          <el-text type="info" size="small">仅展示自己创建的试卷（含收藏副本）</el-text>
        </div>
        <el-table v-loading="loadingMine" :data="myPapers" stripe>
          <el-table-column prop="name" label="试卷名称" min-width="200" show-overflow-tooltip />
          <el-table-column prop="question_count" label="题量" width="70" align="center" />
          <el-table-column prop="total_score" label="总分" width="70" align="center" />
          <el-table-column prop="duration" label="时长(分)" width="90" align="center" />
          <el-table-column label="来源" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.is_copy" type="warning" size="small">收藏</el-tag>
              <el-tag v-else type="info" size="small">自建</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'PUBLISHED' ? 'success' : 'info'" size="small">
                {{ row.status === 'PUBLISHED' ? '已发布' : '草稿' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="360" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="viewPaper(row)">详情</el-button>              <el-button size="small" type="primary" plain @click="openPublish(row)">发布考试</el-button>
              <el-button size="small" @click="openShares(row)">发布列表</el-button>
              <el-button size="small" @click="exportWord(row, false)">导出Word</el-button>
              <el-button size="small" @click="exportWord(row, true)">含答案</el-button>
              <el-button v-if="row.status !== 'PUBLISHED'" size="small" type="danger" plain @click="removePaper(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="minePage" :page-size="10" :total="mineTotal" layout="total, prev, pager, next" class="pager" @current-change="loadMine" />
      </el-tab-pane>

      <!-- ============ 分享给我的 ============ -->
      <el-tab-pane label="分享给我的" name="shared">
        <el-table v-loading="loadingShared" :data="sharedPapers" stripe>
          <el-table-column prop="name" label="试卷名称" min-width="200" show-overflow-tooltip />
          <el-table-column prop="publisher_name" label="发布人" width="120" />
          <el-table-column prop="question_count" label="题量" width="70" align="center" />
          <el-table-column prop="duration" label="时长(分)" width="90" align="center" />
          <el-table-column prop="share_time" label="发布时间" width="170" />
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="startExam(row)">开始作答</el-button>
              <el-button size="small" @click="previewShared(row)">预览</el-button>
              <el-button size="small" type="warning" plain @click="copyPaper(row)">收藏到我的试卷</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="sharedPage" :page-size="10" :total="sharedTotal" layout="total, prev, pager, next" class="pager" @current-change="loadShared" />
      </el-tab-pane>

      <!-- ============ 题目库 ============ -->
      <el-tab-pane label="题目库" name="questions">
        <div class="toolbar">
          <el-button type="primary" :icon="'CirclePlus'" @click="openAddQuestion">添加题目</el-button>
          <el-input v-model="qKeyword" placeholder="搜索题干" clearable style="width: 220px" @keyup.enter="loadQuestions" @clear="loadQuestions" />
          <el-text type="info" size="small">仅显示已审核通过的题目；添加的题目需管理员审核</el-text>
        </div>
        <el-table v-loading="loadingQ" :data="questions" stripe>
          <el-table-column prop="type" label="题型" width="90">
            <template #default="{ row }">{{ typeLabel(row.type) }}</template>
          </el-table-column>
          <el-table-column prop="content" label="题干" min-width="300" show-overflow-tooltip />
          <el-table-column prop="difficulty" label="难度" width="80" />
          <el-table-column prop="knowledge_point" label="知识点" width="140" show-overflow-tooltip />
        </el-table>
        <el-pagination v-model:current-page="qPage" :page-size="10" :total="qTotal" layout="total, prev, pager, next" class="pager" @current-change="loadQuestions" />
      </el-tab-pane>
    </el-tabs>

    <!-- 组卷弹窗 -->
    <el-dialog v-model="createVisible" title="手动组卷" width="720px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="试卷名称" required>
          <el-input v-model="createForm.name" maxlength="128" placeholder="如：安全生产知识测试" />
        </el-form-item>
        <el-form-item label="考试时长" required>
          <el-radio-group v-model="createForm.duration">
            <el-radio-button :value="30">30 分钟</el-radio-button>
            <el-radio-button :value="60">60 分钟</el-radio-button>
            <el-radio-button :value="90">90 分钟</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="合格线">
          <el-input-number v-model="createForm.pass_score" :min="1" :max="100" /> 分
        </el-form-item>
        <el-form-item label="总分">
          <el-input-number v-model="createForm.total_score" :min="10" :max="500" :step="10" /> 分
        </el-form-item>
        <el-form-item label="选题">
          <div class="pick-area">
            <div class="pick-toolbar">
              <el-input v-model="pickKeyword" placeholder="搜索题干选题" clearable size="small" style="width: 220px" @keyup.enter="loadPickQuestions" />
              <el-button size="small" @click="loadPickQuestions">搜索</el-button>
            </div>
            <el-table v-loading="loadingPick" :data="pickQuestions" height="300" size="small" stripe
                      @selection-change="(rows: { id: number; type: string; content: string }[]) => (pickSelected = rows)">
              <el-table-column type="selection" width="44" />
              <el-table-column prop="type" label="题型" width="80">
                <template #default="{ row }">{{ typeLabel(row.type) }}</template>
              </el-table-column>
              <el-table-column prop="content" label="题干" min-width="260" show-overflow-tooltip />
            </el-table>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" :disabled="!createForm.name || !pickSelected.length" @click="submitCreate">
          组卷（{{ pickSelected.length }} 题）
        </el-button>
      </template>
    </el-dialog>

    <!-- 发布考试弹窗（指定用户：搜索 + 多选） -->
    <el-dialog v-model="publishVisible" :title="`发布考试：${publishTarget?.name ?? ''}`" width="520px" append-to-body>
      <el-text type="info" size="small">选择指定用户（可多选，支持昵称搜索）；发布后对方可直接作答，统计自动归集到您</el-text>
      <el-input v-model="publishKeyword" placeholder="搜索昵称/用户名" clearable style="margin: 12px 0" @input="searchTargets" />
      <el-checkbox-group v-model="publishSelected" class="target-list">
        <el-checkbox v-for="u in targetUsers" :key="u.id" :value="u.id" class="target-item">
          {{ u.name }}（{{ u.username }}）
        </el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="publishVisible = false">取消</el-button>
        <el-button type="primary" :loading="publishing" :disabled="!publishSelected.length" @click="submitPublish">
          发布给 {{ publishSelected.length }} 名用户
        </el-button>
      </template>
    </el-dialog>

    <!-- 发布列表弹窗 -->
    <el-dialog v-model="sharesVisible" :title="`发布列表：${sharesTarget?.name ?? ''}`" width="480px" append-to-body>
      <el-table :data="shares" size="small">
        <el-table-column prop="target_name" label="用户" width="140" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'" size="small">
              {{ row.status === 'ACTIVE' ? '发布中' : '已撤销' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="create_time" label="发布时间" width="170" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button v-if="row.status === 'ACTIVE'" size="small" type="danger" plain @click="revokeShare(row)">撤销</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 添加题目弹窗 -->
    <el-dialog v-model="addQVisible" title="添加题目（提交后需管理员审核）" width="680px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="题型" required>
          <el-select v-model="addQ.type" style="width: 160px">
            <el-option v-for="t in QUESTION_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="题干" required>
          <el-input v-model="addQ.content" type="textarea" :rows="3" maxlength="2000" show-word-limit />
        </el-form-item>
        <el-form-item v-if="['SINGLE', 'MULTIPLE'].includes(addQ.type)" label="选项" required>
          <div class="opt-list">
            <div v-for="(_, i) in addQ.options" :key="i" class="opt-row">
              <el-input v-model="addQ.options[i]" :placeholder="`选项 ${'ABCD'[i]}`" style="width: 320px" />
              <el-button v-if="addQ.options.length > 2" size="small" text type="danger" @click="addQ.options.splice(i, 1)">删</el-button>
            </div>
            <el-button size="small" @click="addQ.options.push('')">添加选项</el-button>
          </div>
        </el-form-item>
        <el-form-item v-if="addQ.type === 'JUDGE'" label="答案">
          <el-radio-group v-model="addQ.answer">
            <el-radio value="A">正确</el-radio>
            <el-radio value="B">错误</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-else label="答案" required>
          <el-input v-model="addQ.answer" :placeholder="addQ.type === 'MULTIPLE' ? '多选填字母组合，如 AC' : addQ.type === 'SINGLE' ? '单选填选项字母，如 A' : '填空题多空用分号分隔'" />
        </el-form-item>
        <el-form-item label="解析">
          <el-input v-model="addQ.analysis" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="知识点">
          <el-input v-model="addQ.knowledge_point" placeholder="如：安全生产法" />
        </el-form-item>
        <el-form-item label="难度">
          <el-radio-group v-model="addQ.difficulty">
            <el-radio value="EASY">简单</el-radio>
            <el-radio value="MEDIUM">中等</el-radio>
            <el-radio value="HARD">困难</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addQVisible = false">取消</el-button>
        <el-button type="primary" :loading="addingQ" @click="submitAddQuestion">提交审核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  copySharedPaper, createMyPaper, deleteMyPaper, exportPaperWord, listMyPapers,
  listPaperShares, listSharedPapers, publishMyPaper, revokeMyShare, searchTargetUsers,
} from '@/api/workshop'
import { createQuestion, listQuestions } from '@/api/exam'
import type { SharedPaperItem, UserPaperItem, WorkshopPaperBrief } from '@/types/models/workshop'

const router = useRouter()
const tab = ref('mine')

const QUESTION_TYPES = [
  { value: 'SINGLE', label: '单选题' },
  { value: 'MULTIPLE', label: '多选题' },
  { value: 'JUDGE', label: '判断题' },
  { value: 'FILL', label: '填空题' },
  { value: 'SUBJECTIVE', label: '解答题' },
]
function typeLabel(t: string) {
  return QUESTION_TYPES.find((x) => x.value === t)?.label ?? t
}

// ---------- 我的试卷 ----------
const loadingMine = ref(false)
const myPapers = ref<UserPaperItem[]>([])
const minePage = ref(1)
const mineTotal = ref(0)
async function loadMine() {
  loadingMine.value = true
  try {
    const res = await listMyPapers({ page: minePage.value, page_size: 10 })
    myPapers.value = res.items
    mineTotal.value = res.total
  } finally {
    loadingMine.value = false
  }
}

// ---------- 组卷 ----------
const createVisible = ref(false)
const creating = ref(false)
const createForm = reactive({ name: '', duration: 30, pass_score: 60, total_score: 100 })
const pickKeyword = ref('')
const pickQuestions = ref<{ id: number; type: string; content: string }[]>([])
const pickSelected = ref<{ id: number }[]>([])
const loadingPick = ref(false)
const qPage = ref(1)
const qTotal = ref(0)
const qKeyword = ref('')
const loadingQ = ref(false)
const questions = ref<{ id: number; type: string; content: string; difficulty: string; knowledge_point: string | null }[]>([])

async function loadPickQuestions() {
  loadingPick.value = true
  try {
    const res = await listQuestions({ keyword: pickKeyword.value, page: 1, page_size: 50 })
    pickQuestions.value = res.items
  } finally {
    loadingPick.value = false
  }
}
async function loadQuestions() {
  loadingQ.value = true
  try {
    const res = await listQuestions({ keyword: qKeyword.value, page: qPage.value, page_size: 10 })
    questions.value = res.items
    qTotal.value = res.total
  } finally {
    loadingQ.value = false
  }
}
function openCreate() {
  createForm.name = ''
  createForm.duration = 30
  createForm.pass_score = 60
  createForm.total_score = 100
  pickKeyword.value = ''
  pickSelected.value = []
  createVisible.value = true
  loadPickQuestions()
}
/** 查看试卷详情（复用管理端试卷预览页 /exam/papers/:id 或提示） */
function viewPaper(row: WorkshopPaperBrief) {
  router.push(`/exam/papers/${row.id}`)
}
async function submitCreate() {
  creating.value = true
  try {
    await createMyPaper({
      name: createForm.name,
      duration: createForm.duration as 30 | 60 | 90,
      pass_score: createForm.pass_score,
      total_score: createForm.total_score,
      questions: pickSelected.value.map((q) => ({ question_id: q.id })),
    })
    ElMessage.success('组卷成功')
    createVisible.value = false
    loadMine()
  } catch {
    // 已提示
  } finally {
    creating.value = false
  }
}

// ---------- 发布考试 ----------
const publishVisible = ref(false)
const publishing = ref(false)
const publishTarget = ref<WorkshopPaperBrief | null>(null)
const publishKeyword = ref('')
const publishSelected = ref<number[]>([])
const targetUsers = ref<{ id: number; name: string; username: string }[]>([])
async function searchTargets() {
  const res = await searchTargetUsers(publishKeyword.value)
  targetUsers.value = res.items
}
function openPublish(row: WorkshopPaperBrief) {
  publishTarget.value = row
  publishKeyword.value = ''
  publishSelected.value = []
  publishVisible.value = true
  searchTargets()
}
async function submitPublish() {
  if (!publishTarget.value) return
  publishing.value = true
  try {
    const res = await publishMyPaper(publishTarget.value.id, { target_user_ids: publishSelected.value })
    ElMessage.success(res.message)
    publishVisible.value = false
    loadMine()
  } finally {
    publishing.value = false
  }
}

// ---------- 发布列表 / 撤销 ----------
const sharesVisible = ref(false)
const sharesTarget = ref<WorkshopPaperBrief | null>(null)
const shares = ref<{ target_user_id: number; target_name: string; status: string; create_time: string | null }[]>([])
async function openShares(row: WorkshopPaperBrief) {
  sharesTarget.value = row
  const res = await listPaperShares(row.id)
  shares.value = res.items
  sharesVisible.value = true
}
async function revokeShare(row: { target_user_id: number }) {
  if (!sharesTarget.value) return
  await revokeMyShare(sharesTarget.value.id, row.target_user_id)
  ElMessage.success('已撤销发布')
  openShares(sharesTarget.value)
}

// ---------- 分享给我的 ----------
const loadingShared = ref(false)
const sharedPapers = ref<SharedPaperItem[]>([])
const sharedPage = ref(1)
const sharedTotal = ref(0)
async function loadShared() {
  loadingShared.value = true
  try {
    const res = await listSharedPapers({ page: sharedPage.value, page_size: 10 })
    sharedPapers.value = res.items
    sharedTotal.value = res.total
  } finally {
    loadingShared.value = false
  }
}
async function startExam(row: SharedPaperItem) {
  const { startExam } = await import('@/api/exam')
  try {
    const res = await startExam({ paper_id: row.id })
    router.push(`/exams/${res.record_id}`)
  } catch {
    // 已提示
  }
}
async function copyPaper(row: SharedPaperItem) {
  const res = await copySharedPaper(row.id)
  ElMessage.success(`已收藏到我的试卷：${res.name}`)
}
async function previewShared(row: SharedPaperItem) {
  ElMessage.info('预览：打开试卷详情确认后作答')
  router.push(`/exams/papers/${row.id}/shared`)
}

// ---------- 导出 / 删除 ----------
async function exportWord(row: WorkshopPaperBrief, withAnswers: boolean) {
  const blob = await exportPaperWord(row.id, withAnswers)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${row.name}${withAnswers ? '（含答案）' : ''}.docx`
  a.click()
  URL.revokeObjectURL(url)
}
async function removePaper(row: WorkshopPaperBrief) {
  try {
    await ElMessageBox.confirm(`确认删除试卷「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  await deleteMyPaper(row.id)
  ElMessage.success('已删除')
  loadMine()
}

// ---------- 添加题目 ----------
const addQVisible = ref(false)
const addingQ = ref(false)
const addQ = reactive({
  type: 'SINGLE', content: '', options: ['', '', '', ''] as string[],
  answer: '', analysis: '', knowledge_point: '', difficulty: 'EASY',
})
function openAddQuestion() {
  Object.assign(addQ, { type: 'SINGLE', content: '', options: ['', '', '', ''], answer: '', analysis: '', knowledge_point: '', difficulty: 'EASY' })
  addQVisible.value = true
}
async function submitAddQuestion() {
  if (!addQ.content.trim()) return ElMessage.warning('请填写题干')
  if (['SINGLE', 'MULTIPLE'].includes(addQ.type) && addQ.options.some((o) => !o.trim())) {
    return ElMessage.warning('选项不能为空')
  }
  if (!addQ.answer.trim()) return ElMessage.warning('请填写答案')
  addingQ.value = true
  try {
    const res = await createQuestion({
      type: addQ.type as never,
      content: addQ.content.trim(),
      answer: addQ.answer.trim(),
      analysis: addQ.analysis.trim() || '',
      knowledge_point: addQ.knowledge_point.trim() || '',
      difficulty: addQ.difficulty as never,
      options: ['SINGLE', 'MULTIPLE'].includes(addQ.type) ? addQ.options.map((o) => o.trim()) : null,
    })
    ElMessage.success(`已提交审核（题目 #${res.id}），管理员审核通过后进入题库`)
    addQVisible.value = false
  } finally {
    addingQ.value = false
  }
}

onMounted(() => {
  loadMine()
  loadShared()
  loadQuestions()
})
</script>

<style scoped>
.exam-workshop {
  max-width: 1160px;
  margin: 0 auto;
}
.page-head {
  margin-bottom: 16px;
}
.page-title {
  margin: 0 0 4px;
  font-size: 20px;
}
.ws-tabs {
  margin-top: 8px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.pager {
  margin-top: 14px;
  justify-content: flex-end;
}
.pick-area {
  width: 100%;
}
.pick-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.target-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 260px;
  overflow-y: auto;
}
.opt-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}
.opt-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
