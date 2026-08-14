<template>
  <div class="exam-taking" v-loading="loading">
    <!-- 记录不存在 / 无权限 / 试卷被删除 -->
    <el-result v-if="loadError" icon="warning" title="无法进入该考试" subtitle="考试记录不存在或无权限">
      <template #extra>
        <el-button type="primary" @click="router.replace('/exams')">返回选卷</el-button>
      </template>
    </el-result>

    <template v-else-if="sheet && currentQuestion">
      <!-- 顶部：标题 + 倒计时 + 保存状态 + 交卷 -->
      <div class="exam-header">
        <div class="header-left">
          <div class="paper-title">{{ sheet.paper_name }}</div>
          <el-tag size="small" type="info">第 {{ currentIndex + 1 }}/{{ questions.length }} 题</el-tag>
        </div>
        <div class="header-right">
          <ExamCountdown :seconds="sheet.remaining_seconds" :total="sheet.duration * 60" @finish="handleCountdownFinish" />
          <el-tag v-if="savingStatus === 'saving'" size="small" type="warning">保存中…</el-tag>
          <el-tag v-else-if="savingStatus === 'saved'" size="small" type="success">已保存</el-tag>
          <el-tag v-else-if="savingStatus === 'error'" size="small" type="danger">保存失败</el-tag>
          <el-button type="danger" :loading="submitting" @click="onManualSubmit">交 卷</el-button>
        </div>
      </div>

      <!-- 切屏警告条 -->
      <el-alert
        v-if="cheatCount > 0"
        class="cheat-bar"
        type="warning"
        show-icon
        :closable="false"
      >
        检测到切屏 {{ cheatCount }} 次，超过 3 次将自动交卷，请专注作答！
      </el-alert>

      <!-- 主体：左侧答题卡 + 右侧题目 -->
      <div class="exam-body">
        <aside class="question-nav">
          <div class="nav-title">答题卡</div>
          <div class="nav-progress">已答 {{ answeredCount }} / {{ questions.length }} 题</div>
          <div class="nav-grid">
            <button
              v-for="(q, i) in questions"
              :key="q.id"
              type="button"
              class="nav-btn"
              :class="{ current: i === currentIndex, answered: isAnswered(q.id) }"
              @click="goTo(i)"
            >
              {{ q.seq }}
            </button>
          </div>
          <div class="nav-legend">
            <span class="legend-dot answered-dot"></span>已答
            <span class="legend-dot current-dot"></span>当前
            <span class="legend-dot unanswer-dot"></span>未答
          </div>
        </aside>

        <section class="question-area">
          <div class="q-card">
            <div class="q-head">
              <el-tag size="small" :type="typeTag(currentQuestion.type)">{{ questionTypeLabel(currentQuestion.type) }}</el-tag>
              <span class="q-seq">第 {{ currentQuestion.seq }} 题</span>
              <span class="q-score">{{ currentQuestion.score }} 分</span>
            </div>

            <div class="q-content">{{ currentQuestion.content }}</div>

            <!-- SINGLE / JUDGE -->
            <el-radio-group
              v-if="isSingle || isJudge"
              :model-value="currentAnswered"
              class="opt-list"
              @change="onRadioChange"
            >
              <el-radio v-for="opt in displayOptions(currentQuestion)" :key="opt.value" :value="opt.value" class="opt-item" border>
                {{ opt.label }}
              </el-radio>
            </el-radio-group>

            <!-- MULTIPLE -->
            <el-checkbox-group v-else-if="isMultiple" v-model="multipleValue" class="opt-list">
              <el-checkbox v-for="opt in displayOptions(currentQuestion)" :key="opt.value" :value="opt.value" class="opt-item" border>
                {{ opt.label }}
              </el-checkbox>
            </el-checkbox-group>

            <!-- FILL -->
            <div v-else-if="isFill" class="fill-wrap">
              <div class="fill-hint">多个空请按顺序填写，作答以中文分号「；」分隔</div>
              <el-input
                v-for="(slotVal, i) in currentFill"
                :key="i"
                :model-value="slotVal"
                class="fill-input"
                :placeholder="`第 ${i + 1} 空`"
                @update:model-value="fillUpdater(i)"
              />
            </div>
          </div>

          <div class="q-footer">
            <el-button :disabled="currentIndex === 0" @click="goTo(currentIndex - 1)">上一题</el-button>
            <el-button v-if="currentIndex < questions.length - 1" type="primary" @click="goTo(currentIndex + 1)">下一题</el-button>
            <el-button v-else type="danger" @click="onManualSubmit">交 卷</el-button>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { resumeExam, saveExamAnswers, submitExam, switchExam } from '@/api/exam'
import type { ExamSheet, QuestionType, ResultSheet } from '@/types/models/exam'
import { questionTypeLabel } from '@/utils/constants/question'
import ExamCountdown from '@/components/exam/ExamCountdown.vue'

/** resume/save 响应判别：state==='ONGOING' 即进行中试卷视图（ExamSheet） */
function isOngoingSheet(d: ExamSheet | ResultSheet): d is ExamSheet {
  return d.state === 'ONGOING'
}

const route = useRoute()
const router = useRouter()
const recordId = Number(route.params.recordId)

/** 切屏阈值（与后端 CHEAT_LIMIT 对齐：>3 即第 4 次触发自动交卷） */
const CHEAT_LIMIT = 3
/** 自动保存档位：每 15s 心跳检查一次脏数据 */
const AUTOSAVE_INTERVAL = 15
/** 切屏双计数去重窗口（ms） */
const CHEAT_DEDUP_MS = 2000

const loading = ref(true)
const loadError = ref(false)
const sheet = ref<ExamSheet | null>(null)
const currentIndex = ref(0)
const answersMap = ref(new Map<number, string>())
const dirtySet = ref(new Set<number>())
const saving = ref(false)
const submitting = ref(false)
const savingStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const cheatCount = ref(0)
const fillInputs = ref<Record<number, string[]>>({})
const questionEntryTime = ref(Date.now())

// ---- 心跳：1s 递增，模 15s 触发自动保存 ----
let heartbeat: number | null = null
let heartbeatCount = 0
let lastCheatTs = 0

const questions = computed(() => sheet.value?.questions ?? [])
const currentQuestion = computed(() => questions.value[currentIndex.value])

const isSingle = computed(() => currentQuestion.value?.type === 'SINGLE')
const isMultiple = computed(() => currentQuestion.value?.type === 'MULTIPLE')
const isJudge = computed(() => currentQuestion.value?.type === 'JUDGE')
const isFill = computed(() => currentQuestion.value?.type === 'FILL')

const currentAnswered = computed(() => {
  const q = currentQuestion.value
  if (!q) return ''
  return answersMap.value.get(q.id) ?? ''
})

const multipleValue = computed({
  get: () => (currentAnswered.value ? currentAnswered.value.split(',') : []),
  set: (v: string[]) => {
    const q = currentQuestion.value
    if (!q) return
    setAnswer(q.id, v.join(','))
  },
})

/** 当前填空题输入框数组（按已存答案分空数懒初始化） */
const currentFill = computed(() => {
  const q = currentQuestion.value
  if (!q) return []
  const qid = q.id
  if (!fillInputs.value[qid]) {
    const saved = answersMap.value.get(qid)
    const parts = saved && saved.length ? saved.split(';') : []
    const count = Math.max(fillSlotCount(qid), parts.length, 1)
    fillInputs.value[qid] = Array.from({ length: count }, (_, i) => parts[i] ?? '')
  }
  return fillInputs.value[qid]
})

const answeredCount = computed(() => {
  let c = 0
  for (const q of questions.value) {
    const a = answersMap.value.get(q.id)
    if (a && a.length > 0) c++
  }
  return c
})

// ---------- 工具 ----------

function typeTag(t: QuestionType): 'primary' | 'success' | 'warning' | 'info' | 'danger' {
  switch (t) {
    case 'SINGLE':
      return 'primary'
    case 'MULTIPLE':
      return 'success'
    case 'JUDGE':
      return 'warning'
    case 'FILL':
      return 'info'
  }
}

/** 选项 → 作答值（大写字母标签；选项无字母前缀时按序号推导） */
function optionValue(opt: string, idx: number): string {
  const first = opt.trim().charAt(0).toUpperCase()
  if (/^[A-H]$/.test(first)) return first
  return String.fromCharCode(65 + idx)
}

function displayOptions(q: { type: QuestionType; options: string[] | null }): { value: string; label: string }[] {
  let list = q.options && q.options.length > 0 ? q.options : []
  if (q.type === 'JUDGE' && list.length !== 2) list = ['A 正确', 'B 错误']
  return list.map((o, i) => ({ value: optionValue(o, i), label: o }))
}

/** FILL 空位数：题干占位符（（1）（2）/①②…）识别，失败回退 1 */
function fillSlotCount(qid: number): number {
  const q = questions.value.find((x) => x.id === qid)
  const content = q?.content ?? ''
  const m = content.match(/[（(](\d+)[）)]|①|②|③|④|⑤|⑥|⑦|⑧|⑨|⑩|【\s*(\d+)\s*空\s*】/g)
  return m?.length ?? 0
}

function isAnswered(qid: number): boolean {
  const a = answersMap.value.get(qid)
  return !!a && a.length > 0
}

function setAnswer(qid: number, val: string) {
  answersMap.value.set(qid, val)
  dirtySet.value.add(qid)
  savingStatus.value = 'idle'
}

// ---------- 作答控件 ----------

function onRadioChange(v: string | number | boolean) {
  const q = currentQuestion.value
  if (!q) return
  setAnswer(q.id, String(v))
}

function onFillChange(idx: number, v: string) {
  const q = currentQuestion.value
  if (!q) return
  const arr = currentFill.value
  arr[idx] = v
  setAnswer(q.id, arr.join(';'))
}

/** el-input update:model-value → 归一到字符串的处理器工厂 */
function fillUpdater(idx: number) {
  return (v: string | number | null) => onFillChange(idx, v == null ? '' : String(v))
}

// ---------- 导航 ----------

async function goTo(idx: number) {
  if (idx < 0 || idx >= questions.value.length || idx === currentIndex.value) return
  // 切题自动保存：仅当在本大题停留超过 15s 才触发增量保存
  if (Date.now() - questionEntryTime.value >= AUTOSAVE_INTERVAL * 1000) {
    await saveDirty()
  }
  currentIndex.value = idx
  questionEntryTime.value = Date.now()
}

// ---------- 自动保存 ----------

async function saveDirty(): Promise<boolean> {
  if (!sheet.value) return false
  if (dirtySet.value.size === 0) return true
  if (saving.value) return false
  saving.value = true
  savingStatus.value = 'saving'
  const qids = [...dirtySet.value]
  const answers = qids.map((qid) => ({ question_id: qid, user_answer: answersMap.value.get(qid) ?? '' }))
  try {
    const data = await saveExamAnswers(recordId, { answers })
    if (data.state === 'SUBMITTED') {
      // 被超时/切屏自动交卷抢先
      ElMessage.warning('考试已被自动交卷，正在查看成绩单')
      await leaveToResult()
      return false
    }
    for (const qid of qids) dirtySet.value.delete(qid)
    savingStatus.value = 'saved'
    sheet.value = data
    return true
  } catch {
    // 保留 dirtySet，下一触发点重试
    savingStatus.value = 'error'
    return false
  } finally {
    saving.value = false
  }
}

function startHeartbeat() {
  stopHeartbeat()
  heartbeatCount = 0
  heartbeat = window.setInterval(() => {
    heartbeatCount++
    if (heartbeatCount >= AUTOSAVE_INTERVAL) {
      heartbeatCount = 0
      if (dirtySet.value.size > 0) void saveDirty()
    }
  }, 1000)
}

function stopHeartbeat() {
  if (heartbeat !== null) {
    window.clearInterval(heartbeat)
    heartbeat = null
  }
}

// ---------- 防切屏 ----------

function onVisibilityChange() {
  if (document.hidden) reportCheat()
}

function onWindowBlur() {
  // 与 visibilitychange 去重：blur 时页面仍可见才计一次（如切到其他窗口）
  if (!document.hidden) reportCheat()
}

function reportCheat() {
  if (!sheet.value) return
  const now = Date.now()
  if (now - lastCheatTs < CHEAT_DEDUP_MS) return
  lastCheatTs = now
  cheatCount.value += 1
  void sendSwitch(cheatCount.value)
}

async function sendSwitch(n: number) {
  try {
    const res = await switchExam(recordId, { cheat_count: n })
    if ((res as { state?: 'ONGOING' | 'SUBMITTED' }).state === 'SUBMITTED') {
      // 切屏超限自动交卷
      cheatCount.value = CHEAT_LIMIT + 1
      await ElMessageBox.alert('切屏超过 3 次，已自动交卷', '提示', { type: 'warning' }).catch(() => {})
      await leaveToResult()
      return
    }
    // 服务端 max 合并后的权威计数与倒计时校正
    cheatCount.value = res.cheat_count
    if (sheet.value) sheet.value.remaining_seconds = res.remaining_seconds
  } catch {
    // 上报失败忽略：本地计数保留，下次上报由服务端 max 合并
  }
}

function addListeners() {
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('blur', onWindowBlur)
  window.addEventListener('beforeunload', onBeforeUnload)
}

function removeListeners() {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('blur', onWindowBlur)
  window.removeEventListener('beforeunload', onBeforeUnload)
}

// ---------- beforeunload 尽力保存 ----------

function onBeforeUnload() {
  if (!sheet.value || dirtySet.value.size === 0) return
  const answers = [...dirtySet.value].map((qid) => ({ question_id: qid, user_answer: answersMap.value.get(qid) ?? '' }))
  const token = localStorage.getItem('shudao_token') ?? ''
  const body = JSON.stringify({ answers })
  try {
    void fetch(`/api/v1/exams/${recordId}/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body,
      keepalive: true,
    })
  } catch {
    // 尽力而为，失败忽略
  }
}

// ---------- 交卷 ----------

async function handleCountdownFinish() {
  ElMessage.warning('考试时间到，正在自动交卷…')
  await submitAll()
}

async function onManualSubmit() {
  const unanswered = questions.value.length - answeredCount.value
  try {
    await ElMessageBox.confirm(
      `共 ${questions.value.length} 题，已答 ${answeredCount.value} 题，未答 ${unanswered} 题。确认交卷吗？交卷后不可修改。`,
      '交卷确认',
      { type: 'warning', confirmButtonText: '确认交卷', cancelButtonText: '继续作答' },
    )
  } catch {
    return
  }
  await submitAll()
}

async function submitAll() {
  if (!sheet.value) return
  if (submitting.value) return
  submitting.value = true
  const answers = questions.value.map((q) => ({ question_id: q.id, user_answer: answersMap.value.get(q.id) ?? '' }))
  try {
    const result = await submitExam(recordId, { answers })
    if (result.state === 'SUBMITTED') {
      await leaveToResult()
    }
  } catch {
    ElMessage.error('交卷失败，请重试')
  } finally {
    submitting.value = false
  }
}

async function leaveToResult() {
  cleanup()
  await router.replace(`/exams/${recordId}/result`)
}

function cleanup() {
  stopHeartbeat()
  removeListeners()
}

// ---------- 初始化：resume 恢复 ----------

async function load() {
  loading.value = true
  try {
    const data = await resumeExam(recordId)
    if (!isOngoingSheet(data)) {
      // 已交卷，直接进成绩单
      ElMessage.info('该考试已交卷，正在查看成绩单')
      await router.replace(`/exams/${recordId}/result`)
      return
    }
    sheet.value = data
    answersMap.value = new Map(data.answers.map((a) => [a.question_id, a.user_answer]))
    dirtySet.value.clear()
    cheatCount.value = data.cheat_count
    currentIndex.value = 0
    questionEntryTime.value = Date.now()
    fillInputs.value = {}
    startHeartbeat()
    addListeners()
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)

onBeforeUnmount(() => {
  cleanup()
})
</script>

<style scoped>
.exam-taking {
  padding: 4px;
  min-height: 400px;
}

.exam-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.paper-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.cheat-bar {
  margin-bottom: 12px;
}

.exam-body {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.question-nav {
  width: 220px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 10px;
  padding: 14px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.nav-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 6px;
}

.nav-progress {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}

.nav-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
}

.nav-btn {
  height: 34px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: #fff;
  color: var(--el-text-color-regular);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.nav-btn:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.nav-btn.current {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
}

.nav-btn.answered {
  background: var(--el-color-success);
  border-color: var(--el-color-success);
  color: #fff;
}

.nav-btn.answered.current {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
}

.nav-legend {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  display: inline-block;
}

.answered-dot {
  background: var(--el-color-success);
  margin-left: 2px;
}

.current-dot {
  background: var(--el-color-primary);
}

.unanswer-dot {
  border: 1px solid var(--el-border-color);
  background: #fff;
}

.question-area {
  flex: 1;
  min-width: 0;
}

.q-card {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  min-height: 320px;
}

.q-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.q-seq {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.q-score {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.q-content {
  font-size: 15px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
  margin-bottom: 20px;
  white-space: pre-wrap;
  word-break: break-word;
}

.opt-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.opt-item {
  width: 100%;
  margin-right: 0;
  height: auto;
  padding: 10px 14px;
  white-space: normal;
  line-height: 1.5;
  color: var(--el-text-color-primary);
}

.fill-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.fill-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.q-footer {
  margin-top: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
