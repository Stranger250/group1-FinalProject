<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import ChatSidebar from '@/components/chat/ChatSidebar.vue'
import ChatInputBar from '@/components/chat/ChatInputBar.vue'
import GenDocDialog from '@/components/chat/GenDocDialog.vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import CitationPanel from '@/components/chat/CitationPanel.vue'
import ArticleDialog from '@/components/chat/ArticleDialog.vue'
import { useChatStore } from '@/store/modules/chat'
import type { ChatCitation, UiChatMessage } from '@/store/modules/chat'

const chatStore = useChatStore()

/** 空对话欢迎态：展示引导 + 快捷提问 */
const isWelcome = computed(() => chatStore.messages.length === 0)

// ---------------- 滚动 ----------------
const listRef = ref<HTMLDivElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

/** 内容/状态变化（含流式 delta）时跟随滚动到底部 */
watch(
  () => chatStore.messages.map((m) => `${m.content}|${m.status}`).join('\n'),
  scrollToBottom,
)

// ---------------- 发送 / 停止 ----------------
function onSend(text: string, file?: { text: string; filename: string } | null) {
  void chatStore.sendMessage(text, file ?? null)
}

// ---------------- O12 生成文档 ----------------
const genDocVisible = ref(false)

// ---------------- 反馈 ----------------
function onFeedback(m: UiChatMessage, value: 1 | -1) {
  if (m.id == null) return
  const next = m.feedback === value ? 0 : value
  void chatStore.setFeedback(m.id, next)
}

// ---------------- 查看原文 ----------------
const articleVisible = ref(false)
const articleDocId = ref('')
const articleArticleNo = ref('')

function openArticle(c: ChatCitation) {
  if (!c.clickable || !c.docId || !c.articleNo) return
  articleDocId.value = c.docId
  articleArticleNo.value = c.articleNo
  articleVisible.value = true
}

onMounted(() => {
  void chatStore.fetchConversations()
})
</script>

<template>
  <div class="ai-assistant">
    <ChatSidebar class="sidebar" />

    <div class="chat-main">
      <!-- 工具栏：O12 生成文档 -->
      <div class="chat-toolbar">
        <div class="toolbar-title">AI 智能助手</div>
        <el-button size="small" type="primary" plain @click="genDocVisible = true">
          <el-icon class="mr-1"><Document /></el-icon>生成文档（Word/PPT）
        </el-button>
      </div>

      <!-- 欢迎态 -->
      <div v-if="isWelcome" class="welcome">
        <div class="welcome-icon">
          <el-icon :size="48"><MagicStick /></el-icon>
        </div>
        <div class="welcome-title">你好，我是蜀道法规助手</div>
        <div class="welcome-desc">基于安全生产法规知识库，解答你的安全生产相关疑问</div>
      </div>

      <!-- 消息列表 -->
      <div v-else ref="listRef" class="message-list">
        <div v-for="(m, i) in chatStore.messages" :key="i" class="msg-row" :class="m.role">
          <!-- 头像 -->
          <div class="msg-avatar">
            <el-icon :size="18">
              <User v-if="m.role === 'user'" />
              <ChatLineRound v-else />
            </el-icon>
          </div>

          <div class="msg-content">
            <div class="msg-bubble" :class="m.role">
              <!-- 用户消息：纯文本 -->
              <template v-if="m.role === 'user'">
                <div v-if="m.fileName" class="user-file-tag">
                  <el-icon :size="13"><Document /></el-icon>{{ m.fileName }}
                </div>
                <div class="user-text">{{ m.content }}</div>
                <div v-if="m.status === 'sending'" class="msg-note">发送中…</div>
                <div v-if="m.error" class="msg-error">{{ m.error }}</div>
              </template>

              <!-- AI 回答：markdown + 引用 + 反馈 -->
              <template v-else>
                <MarkdownRenderer
                  :text="m.content"
                  :loading="m.status === 'streaming'"
                  class="ai-markdown"
                />
                <CitationPanel :citations="m.citations" @view="openArticle" />
                <div v-if="m.error" class="msg-error">{{ m.error }}</div>

                <!-- 反馈（需拿到后端 message id 后可用） -->
                <div v-if="m.id != null" class="feedback-row">
                  <span class="feedback-label">这个回答对你有帮助吗？</span>
                  <el-button
                    text
                    class="fb-btn"
                    :class="{ active: m.feedback === 1 }"
                    @click="onFeedback(m, 1)"
                  >
                    <el-icon><CircleCheck /></el-icon>有用
                  </el-button>
                  <el-button
                    text
                    class="fb-btn"
                    :class="{ active: m.feedback === -1 }"
                    @click="onFeedback(m, -1)"
                  >
                    <el-icon><CircleClose /></el-icon>没用
                  </el-button>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入栏 -->
      <ChatInputBar :show-quick="isWelcome" class="input-bar" @send="onSend" />
    </div>

    <!-- 查看原文弹窗 -->
    <ArticleDialog v-model="articleVisible" :doc-id="articleDocId" :article-no="articleArticleNo" />

    <!-- O12 生成文档弹窗 -->
    <GenDocDialog v-model="genDocVisible" />
  </div>
</template>

<style scoped>
.ai-assistant {
  height: calc(100vh - 88px);
  display: flex;
  gap: 12px;
}
.sidebar {
  flex-shrink: 0;
}
.chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background-color: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  overflow: hidden;
}

/* ---------- 工具栏（O12） ---------- */
.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
.toolbar-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.mr-1 {
  margin-right: 4px;
}

/* ---------- 欢迎态 ---------- */
.welcome {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
}
.welcome-icon {
  color: var(--el-color-primary);
  margin-bottom: 6px;
}
.welcome-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.welcome-desc {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

/* ---------- 消息列表 ---------- */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}
.msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}
.msg-row.user {
  justify-content: flex-end;
}
.msg-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.msg-row.user .msg-avatar {
  order: 2;
  background-color: var(--el-color-primary);
}
.msg-row.assistant .msg-avatar {
  background: linear-gradient(135deg, #1e5a52, #4a8a80);
}
.msg-content {
  max-width: 78%;
  min-width: 0;
}
.msg-row.user .msg-content {
  order: 1;
  display: flex;
  justify-content: flex-end;
}
.msg-bubble {
  padding: 10px 14px;
  border-radius: 10px;
  line-height: 1.7;
}
.msg-bubble.user {
  background-color: var(--el-color-primary);
  color: #fff;
  border-top-right-radius: 2px;
}
.msg-bubble.assistant {
  background-color: var(--el-bg-color-page);
  border: 1px solid var(--el-border-color-lighter);
  border-top-left-radius: 2px;
}
.user-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.user-file-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
  padding: 2px 10px;
  background-color: rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  font-size: 12px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ai-markdown {
  font-size: 14px;
}
.msg-note {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
  margin-top: 4px;
}
.msg-error {
  font-size: 12px;
  color: var(--el-color-danger);
  margin-top: 8px;
}

/* ---------- 反馈 ---------- */
.feedback-row {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed var(--el-border-color-light);
}
.feedback-label {
  font-size: 12px;
  color: #a5acaa;
  margin-right: 6px;
}
.fb-btn {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 2px 6px;
  height: auto;
}
.fb-btn.active {
  color: var(--el-color-primary);
}
</style>
