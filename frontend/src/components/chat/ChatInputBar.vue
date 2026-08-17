<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { quickQuestions, uploadChatFile } from '@/api/ai'
import type { QuickQuestion } from '@/types/models/chat'
import { useChatStore } from '@/store/modules/chat'

const props = withDefaults(
  defineProps<{
    /** 对话为空时展示快捷提问 chips */
    showQuick?: boolean
  }>(),
  { showQuick: false },
)

const emit = defineEmits<{ (e: 'send', text: string, file?: { text: string; filename: string } | null): void }>()

const chatStore = useChatStore()
const text = ref('')
const quick = ref<QuickQuestion[]>([])

/** O11 上传文档：{ filename, text } 发送时随消息携带；解析中禁止再次上传 */
const attachedFile = ref<{ filename: string; text: string } | null>(null)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(async () => {
  try {
    quick.value = await quickQuestions()
  } catch {
    quick.value = []
  }
})

function handleSend() {
  const t = text.value.trim()
  if (!t || chatStore.streaming) return
  emit('send', t, attachedFile.value ? { ...attachedFile.value } : null)
  text.value = ''
  attachedFile.value = null
}

function onQuick(q: QuickQuestion) {
  if (chatStore.streaming) return
  emit('send', q.question, null)
  text.value = ''
}

// ---------------- O11 文件上传 ----------------
const ACCEPT = '.txt,.md,.pdf,.docx'

function pickFile() {
  if (uploading.value || chatStore.streaming) return
  fileInput.value?.click()
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (attachedFile.value) {
    ElMessage.warning('一次只能携带一个文档，请先移除当前附件')
    return
  }
  uploading.value = true
  try {
    const res = await uploadChatFile(file)
    attachedFile.value = { filename: res.filename, text: res.text }
    ElMessage.success(`已解析 ${res.filename}（${res.chars} 字${res.truncated ? '，超长已截断' : ''}）`)
  } catch {
    /* 错误已由 request 全局提示 */
  } finally {
    uploading.value = false
  }
}

function removeFile() {
  attachedFile.value = null
}
</script>

<template>
  <div class="chat-input-bar">
    <transition name="el-fade-in">
      <div v-if="props.showQuick && quick.length" class="quick-wrap">
        <div class="quick-label">快捷提问</div>
        <div class="quick-chips">
          <el-tag
            v-for="(q, i) in quick"
            :key="i"
            class="quick-chip"
            effect="plain"
            round
            :disabled="chatStore.streaming"
            @click="onQuick(q)"
          >
            {{ q.question }}
          </el-tag>
        </div>
      </div>
    </transition>

    <!-- O11 附件条 -->
    <transition name="el-fade-in">
      <div v-if="attachedFile || uploading" class="attach-bar">
        <template v-if="uploading">
          <el-icon class="attach-icon" color="var(--el-color-primary)"><Loading /></el-icon>
          <span class="attach-name">正在解析文档…</span>
        </template>
        <template v-else>
          <el-icon class="attach-icon" color="var(--el-color-primary)"><Document /></el-icon>
          <span class="attach-name">{{ attachedFile?.filename }}</span>
          <span class="attach-tip">已携带（回答可引用该文档内容）</span>
          <el-button text size="small" class="attach-remove" @click="removeFile">
            <el-icon><Close /></el-icon>移除
          </el-button>
        </template>
      </div>
    </transition>

    <div class="input-row">
      <el-input
        v-model="text"
        type="textarea"
        maxlength="2000"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请输入你的问题，按 Enter 发送，Shift + Enter 换行"
        class="chat-textarea"
        :disabled="chatStore.streaming"
        @keydown.enter.exact.prevent="handleSend"
      />
      <div class="send-area">
        <el-button class="upload-btn" :disabled="chatStore.streaming || uploading" @click="pickFile">
          <el-icon class="mr-1"><Upload /></el-icon>上传文档
        </el-button>
        <input
          ref="fileInput"
          type="file"
          :accept="ACCEPT"
          class="hidden-file-input"
          @change="onFileChange"
        />
        <el-button v-if="chatStore.streaming" class="stop-btn" @click="chatStore.stopStreaming()">
          <el-icon class="mr-1"><VideoPause /></el-icon>停止生成
        </el-button>
        <el-button
          v-else
          type="primary"
          class="send-btn"
          :disabled="!text.trim()"
          @click="handleSend"
        >
          <el-icon class="mr-1"><Promotion /></el-icon>发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-input-bar {
  padding: 12px 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  background-color: #fff;
  border-radius: 0 0 10px 10px;
}
.quick-wrap {
  margin-bottom: 10px;
}
.quick-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.quick-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.quick-chip {
  cursor: pointer;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.quick-chip:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

/* ---------- O11 附件条 ---------- */
.attach-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding: 6px 10px;
  background-color: var(--el-color-primary-light-9);
  border: 1px dashed var(--el-color-primary-light-5);
  border-radius: 8px;
  font-size: 13px;
}
.attach-icon {
  flex-shrink: 0;
}
.attach-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attach-tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.attach-remove {
  margin-left: auto;
  color: var(--el-color-danger);
  padding: 0 4px;
  height: auto;
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}
.chat-textarea {
  flex: 1;
}
.send-area {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  padding-bottom: 2px;
}
.upload-btn {
  font-size: 12px;
  padding: 4px 10px;
  height: auto;
}
.hidden-file-input {
  display: none;
}
.mr-1 {
  margin-right: 4px;
}
</style>
