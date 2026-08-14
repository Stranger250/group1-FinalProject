<template>
  <div class="page-container">
    <el-card shadow="never" class="gen-card">
      <template #header>
        <div class="card-title">
          AI 出题
          <span class="card-sub">依据蜀道法规语料生成题目，产出为待审核批次；可上传文档限定出题范围（如培训手册、制度文件）</span>
          <el-link class="go-paper" type="primary" @click="goPaperCreate">已有审核通过的题库？去自动组卷 →</el-link>
        </div>
      </template>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" :disabled="generating">
        <el-form-item label="知识点" prop="knowledge_point">
          <el-input
            v-model="form.knowledge_point"
            maxlength="64"
            show-word-limit
            placeholder="必填，如：高处作业、临时用电、危化品管理"
            style="max-width: 480px"
          />
        </el-form-item>

        <el-form-item label="题型" prop="types">
          <el-checkbox-group v-model="form.types">
            <el-checkbox v-for="t in QUESTION_TYPES" :key="t.value" :value="t.value">
              {{ t.label }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="难度" prop="difficulty">
          <el-radio-group v-model="form.difficulty">
            <el-radio-button v-for="d in DIFFICULTIES" :key="d.value" :value="d.value">
              {{ d.label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="题目数量" prop="count">
          <el-input-number v-model="form.count" :min="5" :max="50" />
          <span class="form-tip">每次生成不少于 5 题；上限 50 题（超过 20 题将分轮生成，耗时相应变长）</span>
        </el-form-item>

        <el-form-item label="限定法规" prop="law_title">
          <el-input
            v-model="form.law_title"
            maxlength="128"
            clearable
            placeholder="选填，如：安全生产法"
            style="max-width: 480px"
          />
        </el-form-item>

        <el-form-item label="参考文档">
          <div class="doc-zone">
            <el-upload
              ref="uploadRef"
              drag
              :show-file-list="false"
              :auto-upload="false"
              accept=".txt,.md,.pdf,.docx"
              :disabled="uploading || generating"
              :on-change="handleDocChange"
            >
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">将文件拖到此处，或<em>点击上传</em></div>
              <template #tip>
                <div class="el-upload__tip">支持 txt / md / pdf / docx，≤ 5MB，解析后随生成请求提交</div>
              </template>
            </el-upload>

            <div v-if="uploading" class="doc-uploading">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>正在解析文档…</span>
            </div>

            <div v-if="docState" class="doc-state">
              <el-icon class="doc-file-icon"><Document /></el-icon>
              <span class="doc-name" :title="docState.filename">{{ docState.filename }}</span>
              <span class="doc-chars">已解析 {{ docState.chars }} 字</span>
              <span v-if="docState.truncated" class="doc-truncated">内容过长已截断至前 5000 字</span>
              <el-button link type="primary" @click="previewVisible = true">查看文本预览</el-button>
              <el-button link type="danger" @click="removeDoc">删除</el-button>
            </div>
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" :loading="generating" :icon="'MagicStick'" @click="handleGenerate">
            {{ generating ? '生成中…' : '开始生成' }}
          </el-button>
        </el-form-item>
      </el-form>

      <div v-if="generating" class="gen-loading">
        <el-skeleton :rows="4" animated />
        <div class="gen-tip">
          <el-icon class="is-loading"><component :is="'Loading'" /></el-icon>
          <span>AI 正在依据法规语料出题（题量越大耗时越长，50 题约需 1~3 分钟），完成后将自动跳转批次详情，请勿关闭页面…</span>
        </div>
      </div>

      <el-dialog
        v-model="previewVisible"
        :title="docState ? `参考文档预览：${docState.filename}` : '参考文档预览'"
        width="640px"
        destroy-on-close
      >
        <div class="doc-preview">{{ docState?.text }}</div>
      </el-dialog>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules, type UploadFile, type UploadInstance } from 'element-plus'
import { DIFFICULTIES, QUESTION_TYPES } from '@/utils/constants'
import { generateQuestions, uploadRefDoc } from '@/api/exam'
import type { GeneratePayload, QuestionDifficulty, QuestionType, RefDocResult } from '@/types/models/exam'

const router = useRouter()
const formRef = ref<FormInstance>()

/** AI 出题 → 自动组卷（互跳入口：出题产池、审核通过后供组卷消费） */
function goPaperCreate(): void {
  router.push({ path: '/exam/papers/create', query: { mode: 'auto' } })
}
const uploadRef = ref<UploadInstance>()
const generating = ref(false)
const uploading = ref(false)
const previewVisible = ref(false)

/** 参考文档上传白名单与大小上限 */
const DOC_ALLOWED_EXT = ['.txt', '.md', '.pdf', '.docx']
const DOC_MAX_SIZE = 5 * 1024 * 1024

/** 已成功解析的参考文档（不存原始 File，解析完成后即可删除选择器内文件） */
const docState = ref<Pick<RefDocResult, 'filename' | 'chars' | 'truncated' | 'text'> | null>(null)

interface GenForm {
  knowledge_point: string
  types: QuestionType[]
  difficulty: QuestionDifficulty
  count: number
  law_title: string
}

const form = reactive<GenForm>({
  knowledge_point: '',
  types: ['SINGLE', 'MULTIPLE'],
  difficulty: 'MEDIUM',
  count: 5,
  law_title: '',
})

const rules = reactive<FormRules>({
  knowledge_point: [{ required: true, message: '请输入知识点', trigger: 'blur' }],
  types: [
    {
      validator: (_r: unknown, _v: unknown, callback) => {
        if (form.types.length === 0) callback(new Error('请至少选择一种题型'))
        else callback()
      },
      trigger: 'change',
    },
  ],
  difficulty: [{ required: true, message: '请选择难度', trigger: 'change' }],
  count: [{ required: true, message: '请输入题目数量', trigger: 'blur' }],
})

/** 取文件名扩展名（小写，含点） */
function docExt(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx).toLowerCase() : ''
}

/** 选择文档后：校验扩展名/大小 → 调解析接口 → 存 docState（失败清空并重置上传区） */
async function handleDocChange(uploadFile: UploadFile): Promise<void> {
  const file = uploadFile.raw
  if (!file) return

  const ext = docExt(file.name)
  if (!DOC_ALLOWED_EXT.includes(ext)) {
    ElMessage.error('仅支持 txt / md / pdf / docx 文件')
    uploadRef.value?.clearFiles()
    return
  }
  if (file.size > DOC_MAX_SIZE) {
    ElMessage.error('文件大小不能超过 5MB')
    uploadRef.value?.clearFiles()
    return
  }

  if (uploading.value) return // 防止重复上传
  uploading.value = true
  try {
    const res = await uploadRefDoc(file)
    if (res.code !== 200) {
      ElMessage.error('文档解析失败')
      docState.value = null
      uploadRef.value?.clearFiles()
      return
    }
    docState.value = {
      filename: res.data.filename,
      chars: res.data.chars,
      truncated: res.data.truncated,
      text: res.data.text,
    }
    ElMessage.success('文档解析成功')
  } catch {
    ElMessage.error('文档解析失败')
    docState.value = null
    uploadRef.value?.clearFiles()
  } finally {
    uploading.value = false
  }
}

/** 删除已上传文档并重置 el-upload 内部 fileList */
function removeDoc(): void {
  docState.value = null
  uploadRef.value?.clearFiles()
}

async function handleGenerate(): Promise<void> {
  const ok = await formRef.value?.validate().catch(() => false)
  if (!ok) return
  generating.value = true
  try {
    const payload: GeneratePayload = {
      knowledge_point: form.knowledge_point.trim(),
      types: form.types,
      difficulty: form.difficulty,
      count: form.count,
      law_title: form.law_title.trim() || null,
    }
    if (docState.value) {
      payload.reference_text = docState.value.text
      payload.reference_title = docState.value.filename
    }
    const res = await generateQuestions(payload)
    ElMessage.success(`已生成 ${res.count} 题，进入批次审核`)
    router.push(`/exam/ai/batches/${res.batch_id}`)
  } catch {
    // 400（无相关条款/校验失败）与 502（AI 输出不合要求）message 已全局提示，停留表单便于改参重试
  } finally {
    generating.value = false
  }
}
</script>

<style scoped>
.gen-card {
  max-width: 720px;
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
.go-paper {
  margin-left: auto;
}
.form-tip {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.doc-zone {
  width: 100%;
}
.doc-uploading {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.doc-state {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--surface);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  font-size: 13px;
}
.doc-file-icon {
  color: var(--el-text-color-secondary);
  font-size: 16px;
}
.doc-name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.doc-chars {
  color: var(--el-text-color-regular);
}
.doc-truncated {
  font-size: 12px;
  color: var(--el-color-danger);
}
.doc-preview {
  max-height: 480px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
  background: var(--surface);
  padding: 12px;
  border-radius: 6px;
}
.gen-loading {
  margin-top: 16px;
  padding: 16px;
  background: var(--surface);
  border-radius: 6px;
}
.gen-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}
</style>
