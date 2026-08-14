<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { quickQuestions } from '@/api/ai'
import type { QuickQuestion } from '@/types/models/chat'
import { useChatStore } from '@/store/modules/chat'

const props = withDefaults(
  defineProps<{
    /** 对话为空时展示快捷提问 chips */
    showQuick?: boolean
  }>(),
  { showQuick: false },
)

const emit = defineEmits<{ (e: 'send', text: string): void }>()

const chatStore = useChatStore()
const text = ref('')
const quick = ref<QuickQuestion[]>([])

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
  emit('send', t)
  text.value = ''
}

function onQuick(q: QuickQuestion) {
  if (chatStore.streaming) return
  emit('send', q.question)
  text.value = ''
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
  padding-bottom: 2px;
}
.mr-1 {
  margin-right: 4px;
}
</style>
