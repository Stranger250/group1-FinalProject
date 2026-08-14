<template>
  <el-dialog
    :model-value="modelValue"
    :title="isEdit ? '编辑题目' : '新建题目'"
    width="640px"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="resetForm"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="88px" :disabled="submitting">
      <el-form-item label="题型" prop="type">
        <el-select
          v-model="form.type"
          :disabled="isEdit"
          placeholder="请选择题型"
          style="width: 200px"
        >
          <el-option v-for="t in QUESTION_TYPES" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
      </el-form-item>

      <el-form-item label="题干" prop="content">
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="3"
          maxlength="1000"
          show-word-limit
          placeholder="请输入题目内容"
        />
      </el-form-item>

      <el-form-item label="选项" prop="options">
        <template v-if="form.type === 'SINGLE' || form.type === 'MULTIPLE'">
          <div class="option-list">
            <div v-for="(_, i) in form.options" :key="i" class="option-row">
              <span class="option-letter">{{ String.fromCharCode(65 + i) }}</span>
              <el-input
                v-model="form.options[i]"
                :placeholder="`选项 ${String.fromCharCode(65 + i)} 内容`"
                maxlength="300"
              />
              <el-button
                text
                type="danger"
                :icon="'Delete'"
                :disabled="form.options.length <= 2"
                @click="removeOption(i)"
              />
            </div>
            <el-button size="small" :icon="'Plus'" @click="addOption">添加选项</el-button>
          </div>
        </template>
        <template v-else-if="form.type === 'JUDGE'">
          <div class="option-readonly">
            <div>A. 正确</div>
            <div>B. 错误</div>
          </div>
        </template>
        <template v-else-if="form.type === 'SUBJECTIVE'">
          <span class="option-tip">解答题无选项，请直接在「答案」中填写参考答案要点</span>
        </template>
        <template v-else>
          <span class="option-tip">填空题无固定选项，请直接填写答案</span>
        </template>
      </el-form-item>

      <el-form-item label="答案" prop="answer">
        <template v-if="form.type === 'SINGLE'">
          <el-radio-group v-model="answerSingle">
            <el-radio v-for="(_, i) in form.options" :key="i" :value="String.fromCharCode(65 + i)">
              {{ String.fromCharCode(65 + i) }}
            </el-radio>
          </el-radio-group>
          <div class="field-tip">{{ typeAnswerHint }}</div>
        </template>
        <template v-else-if="form.type === 'MULTIPLE'">
          <el-checkbox-group v-model="answerMultiple">
            <el-checkbox v-for="(_, i) in form.options" :key="i" :value="String.fromCharCode(65 + i)">
              {{ String.fromCharCode(65 + i) }}
            </el-checkbox>
          </el-checkbox-group>
          <div class="field-tip">{{ typeAnswerHint }}（保存为 A,B 格式）</div>
        </template>
        <template v-else-if="form.type === 'JUDGE'">
          <el-radio-group v-model="answerSingle">
            <el-radio value="A">A. 正确</el-radio>
            <el-radio value="B">B. 错误</el-radio>
          </el-radio-group>
        </template>
        <template v-else-if="form.type === 'SUBJECTIVE'">
          <el-input
            v-model="answerSubjective"
            type="textarea"
            :rows="4"
            maxlength="2000"
            show-word-limit
            placeholder="填写参考答案，多个要点用分号（;）分隔，如：必须佩戴安全帽；高处作业必须系安全带"
          />
          <div class="field-tip">自动阅卷按要点包含命中计分：考生作答包含某要点即得该要点分</div>
        </template>
        <template v-else>
          <el-input v-model="answerFill" placeholder="填空答案，多空用分号（;）分隔" maxlength="64" style="width: 100%" />
        </template>
      </el-form-item>

      <el-form-item label="解析" prop="analysis">
        <el-input
          v-model="form.analysis"
          type="textarea"
          :rows="2"
          maxlength="1000"
          show-word-limit
          placeholder="请填写答案解析"
        />
      </el-form-item>

      <el-form-item label="知识点" prop="knowledge_point">
        <el-input v-model="form.knowledge_point" maxlength="128" placeholder="如：高处作业·安全带使用" />
      </el-form-item>

      <el-form-item label="难度" prop="difficulty">
        <el-select v-model="form.difficulty" placeholder="请选择难度" style="width: 200px">
          <el-option v-for="d in DIFFICULTIES" :key="d.value" :label="d.label" :value="d.value" />
        </el-select>
      </el-form-item>

      <template v-if="!isEdit">
        <el-form-item label="法规标题">
          <el-input v-model="form.source_law_title" maxlength="255" placeholder="选填，如：安全生产法" />
        </el-form-item>
        <el-form-item label="条款编号">
          <el-input v-model="form.source_article_no" maxlength="32" placeholder="选填，如：第 24 条" />
        </el-form-item>
      </template>

      <el-form-item v-if="isEdit" label="状态">
        <el-select v-model="form.status" style="width: 200px">
          <el-option v-for="s in QUESTION_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { DIFFICULTIES, QUESTION_STATUSES, QUESTION_TYPES, questionTypeLabel } from '@/utils/constants'
import { createQuestion, updateQuestion } from '@/api/exam'
import type {
  Question,
  QuestionDifficulty,
  QuestionStatus,
  QuestionType,
  QuestionUpdatePayload,
} from '@/types/models/exam'

const props = defineProps<{
  modelValue: boolean
  /** 传入则编辑，否则新建 */
  question?: Question | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success'): void
}>()

const isEdit = computed(() => !!props.question)

interface FormState {
  type: QuestionType
  content: string
  options: string[]
  analysis: string
  knowledge_point: string
  difficulty: QuestionDifficulty
  source_law_title: string
  source_article_no: string
  status: QuestionStatus
}

const form = reactive<FormState>({
  type: 'SINGLE',
  content: '',
  options: ['', ''],
  analysis: '',
  knowledge_point: '',
  difficulty: 'MEDIUM',
  source_law_title: '',
  source_article_no: '',
  status: 'APPROVED',
})

const answerSingle = ref('')
const answerMultiple = ref<string[]>([])
const answerFill = ref('')
const answerSubjective = ref('')
const submitting = ref(false)
const formRef = ref<FormInstance>()

const typeAnswerHint = computed(() => QUESTION_TYPES.find((t) => t.value === form.type)?.answerHint ?? '')

/** 当前题型是否使用选项（单选/多选） */
function usesOptions(): boolean {
  return form.type === 'SINGLE' || form.type === 'MULTIPLE'
}

function resetForm(): void {
  const q = props.question
  if (q) {
    form.type = q.type
    form.content = q.content ?? ''
    form.options =
      q.type === 'FILL' || q.type === 'SUBJECTIVE'
        ? []
        : (q.options ?? (q.type === 'JUDGE' ? ['正确', '错误'] : ['', '']))
    form.analysis = q.analysis ?? ''
    form.knowledge_point = q.knowledge_point ?? ''
    form.difficulty = q.difficulty
    form.status = q.status
    form.source_law_title = q.source_law_title ?? ''
    form.source_article_no = q.source_article_no ?? ''
    answerSingle.value =
      q.type === 'JUDGE' || q.type === 'SINGLE' ? q.answer.trim().toUpperCase() : ''
    answerMultiple.value =
      q.type === 'MULTIPLE'
        ? q.answer
            .split(/[,，]/)
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean)
        : []
    answerFill.value = q.type === 'FILL' ? q.answer : ''
    answerSubjective.value = q.type === 'SUBJECTIVE' ? q.answer : ''
  } else {
    form.type = 'SINGLE'
    form.content = ''
    form.options = ['', '']
    form.analysis = ''
    form.knowledge_point = ''
    form.difficulty = 'MEDIUM'
    form.status = 'APPROVED'
    form.source_law_title = ''
    form.source_article_no = ''
    answerSingle.value = ''
    answerMultiple.value = []
    answerFill.value = ''
    answerSubjective.value = ''
  }
  formRef.value?.clearValidate()
}

/** 题型切换时清空答案，避免残留 */
watch(
  () => form.type,
  () => {
    answerSingle.value = ''
    answerMultiple.value = []
    answerFill.value = ''
    answerSubjective.value = ''
    formRef.value?.clearValidate()
  },
)

function addOption(): void {
  form.options.push('')
}

function removeOption(i: number): void {
  if (form.options.length <= 2) return
  form.options.splice(i, 1)
  if (answerSingle.value) {
    const letter = String.fromCharCode(65 + i)
    if (answerSingle.value === letter) answerSingle.value = ''
  }
  answerMultiple.value = answerMultiple.value.filter((x) => x !== String.fromCharCode(65 + i))
}

/** 构建选项数组（补字母前缀；判断固定；填空/解答为 null） */
function buildOptions(): string[] | null {
  if (form.type === 'FILL' || form.type === 'SUBJECTIVE') return null
  if (form.type === 'JUDGE') return ['A 正确', 'B 错误']
  return form.options.map((t, i) => `${String.fromCharCode(65 + i)}. ${t.trim()}`)
}

function buildAnswer(): string {
  if (form.type === 'SINGLE') return answerSingle.value.trim().toUpperCase()
  if (form.type === 'MULTIPLE') return answerMultiple.value.map((x) => x.toUpperCase()).join(',')
  if (form.type === 'JUDGE') return answerSingle.value.trim().toUpperCase()
  if (form.type === 'SUBJECTIVE') return answerSubjective.value.trim()
  return answerFill.value.trim()
}

/** 当前答案值（用于校验） */
function currentAnswer(): string {
  return buildAnswer()
}

function optionsValid(): boolean {
  if (form.type === 'SINGLE' || form.type === 'MULTIPLE') {
    if (form.options.length < 2) return false
    if (form.options.some((o) => !o.trim())) return false
  }
  return true
}

function answerValid(): boolean {
  const ans = currentAnswer()
  if (!ans) return false
  if (form.type === 'SINGLE') {
    return form.options.some((_, i) => String.fromCharCode(65 + i) === ans)
  }
  if (form.type === 'MULTIPLE') {
    const letters = form.options.map((_, i) => String.fromCharCode(65 + i))
    return ans.split(',').every((p) => letters.includes(p))
  }
  if (form.type === 'JUDGE') return ans === 'A' || ans === 'B'
  if (form.type === 'SUBJECTIVE') {
    // 解答题：参考答案分号分隔要点，每要点非空
    return ans.split(/[;；]/).every((p) => !!p.trim())
  }
  // FILL：多空用分号分隔，每空非空
  return ans.split(/[;；]/).every((b) => !!b.trim())
}

const rules = reactive<FormRules>({
  type: [{ required: true, message: '请选择题型', trigger: 'change' }],
  content: [{ required: true, message: '请填写题干', trigger: 'blur' }],
  analysis: [{ required: true, message: '请填写解析', trigger: 'blur' }],
  knowledge_point: [{ required: true, message: '请填写知识点', trigger: 'blur' }],
  difficulty: [{ required: true, message: '请选择难度', trigger: 'change' }],
  options: [
    {
      validator: () => (optionsValid() ? undefined : new Error('单选/多选需至少 2 个非空选项')),
      trigger: 'blur',
    },
  ],
  answer: [
    {
      validator: () =>
        answerValid() ? undefined : new Error(questionTypeLabel(form.type) + '答案格式不正确'),
      trigger: 'change',
    },
  ],
})

async function handleSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (!answerValid()) {
    ElMessage.warning('请检查答案格式')
    return
  }
  submitting.value = true
  try {
    if (isEdit.value && props.question) {
      const payload = buildUpdatePayload()
      if (Object.keys(payload).length === 0) {
        emit('update:modelValue', false)
        emit('success')
        return
      }
      await updateQuestion(props.question.id, payload)
      ElMessage.success('题目已更新')
    } else {
      await createQuestion({
        type: form.type,
        content: form.content.trim(),
        options: buildOptions(),
        answer: buildAnswer(),
        analysis: form.analysis.trim(),
        knowledge_point: form.knowledge_point.trim(),
        difficulty: form.difficulty,
        source_law_title: form.source_law_title.trim() || null,
        source_article_no: form.source_article_no.trim() || null,
      })
      ElMessage.success('题目已创建')
    }
    emit('update:modelValue', false)
    emit('success')
  } catch {
    // 后端 message 已全局提示
  } finally {
    submitting.value = false
  }
}

function sameArray(a: string[] | null, b: string[] | null): boolean {
  if (a === null || b === null) return a === b
  if (a.length !== b.length) return false
  return a.every((x, i) => x === b[i])
}

/** 编辑：仅提交变更字段（QuestionUpdate） */
function buildUpdatePayload(): QuestionUpdatePayload {
  const q = props.question!
  const p: QuestionUpdatePayload = {}
  if (form.content.trim() !== (q.content ?? '')) p.content = form.content.trim()
  if (usesOptions()) {
    const built = buildOptions()
    if (!sameArray(q.options, built)) p.options = built
  }
  const ans = buildAnswer()
  if (ans !== q.answer) p.answer = ans
  if (form.analysis.trim() !== (q.analysis ?? '')) p.analysis = form.analysis.trim()
  if (form.knowledge_point.trim() !== (q.knowledge_point ?? '')) p.knowledge_point = form.knowledge_point.trim()
  if (form.difficulty !== q.difficulty) p.difficulty = form.difficulty
  if (form.status !== q.status) p.status = form.status
  return p
}
</script>

<style scoped>
.option-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.option-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.option-letter {
  flex-shrink: 0;
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
.option-readonly {
  color: var(--el-text-color-regular);
  line-height: 1.8;
}
.option-tip {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.field-tip {
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
