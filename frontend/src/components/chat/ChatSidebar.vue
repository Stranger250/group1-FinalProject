<script setup lang="ts">
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useChatStore } from '@/store/modules/chat'
import { formatRelative } from '@/utils/format'

const chatStore = useChatStore()

/** 正在行内重命名的会话 id */
const editingId = ref<number | null>(null)
const editingTitle = ref('')
/** 下拉操作目标会话（@command 前先写入，避免模板内联闭包） */
const menuTarget = ref<{ id: number; title: string } | null>(null)

function startEdit(id: number, title: string) {
  editingId.value = id
  editingTitle.value = title
}

function cancelEdit() {
  editingId.value = null
  editingTitle.value = ''
}

async function commitEdit() {
  const id = editingId.value
  if (id === null) return
  const title = editingTitle.value.trim()
  cancelEdit()
  if (!title) return
  try {
    await chatStore.renameConversation(id, title)
  } catch {
    /* 错误已由 request 全局提示 */
  }
}

async function onDelete(id: number) {
  try {
    await ElMessageBox.confirm('删除后该会话的对话记录将一并清除，确定删除吗？', '删除会话', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await chatStore.removeConversation(id)
  } catch {
    /* 错误已由 request 全局提示 */
  }
}

function onMenuCommand(cmd: unknown) {
  const t = menuTarget.value
  if (!t) return
  if (cmd === 'rename') startEdit(t.id, t.title)
  else if (cmd === 'delete') void onDelete(t.id)
}
</script>

<template>
  <div class="chat-sidebar">
    <div class="sidebar-head">
      <el-button type="primary" class="new-btn" @click="chatStore.newConversation()">
        <el-icon><Plus /></el-icon>
        <span class="btn-text">新建对话</span>
      </el-button>
    </div>

    <div class="sidebar-list">
      <el-skeleton v-if="chatStore.loadingConversations" :rows="8" animated />
      <el-empty
        v-else-if="!chatStore.conversations.length"
        description="暂无会话，点击上方新建"
        :image-size="72"
      />
      <template v-else>
        <div
          v-for="conv in chatStore.conversations"
          :key="conv.id"
          class="conv-item"
          :class="{ active: chatStore.currentId === conv.id }"
          @click="chatStore.selectConversation(conv.id)"
          @dblclick="startEdit(conv.id, conv.title)"
        >
          <el-input
            v-if="editingId === conv.id"
            v-model="editingTitle"
            size="small"
            autofocus
            maxlength="50"
            @click.stop
            @keyup.enter="commitEdit"
            @keyup.esc="cancelEdit"
            @blur="commitEdit"
          />
          <template v-else>
            <div class="conv-info">
              <div class="conv-title" :title="conv.title">{{ conv.title }}</div>
              <div class="conv-time">{{ formatRelative(conv.updated_time) }}</div>
            </div>
            <el-dropdown
              trigger="click"
              class="conv-more-wrap"
              @click.stop="menuTarget = { id: conv.id, title: conv.title }"
              @command="onMenuCommand"
            >
              <el-icon class="conv-more"><MoreFilled /></el-icon>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">
                    <el-icon><EditPen /></el-icon>重命名
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided>
                    <el-icon><Delete /></el-icon>删除
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.chat-sidebar {
  width: 280px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #fff;
  border-radius: 10px;
  border: 1px solid var(--el-border-color-lighter);
  overflow: hidden;
}
.sidebar-head {
  padding: 14px;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2efe8);
}
.new-btn {
  width: 100%;
}
.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.conv-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.15s;
}
.conv-item:hover {
  background-color: var(--el-bg-color-page);
}
.conv-item.active {
  background-color: var(--brand-soft);
}
.conv-info {
  flex: 1;
  min-width: 0;
}
.conv-title {
  font-size: 13px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conv-item.active .conv-title {
  color: var(--el-color-primary);
  font-weight: 600;
}
.conv-time {
  font-size: 11px;
  color: #a5acaa;
  margin-top: 2px;
}
.conv-more-wrap {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  opacity: 0;
  transition: opacity 0.15s;
}
.conv-item:hover .conv-more-wrap {
  opacity: 1;
}
.conv-more {
  padding: 4px;
  border-radius: 4px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}
.conv-more:hover {
  background-color: var(--el-border-color-light);
  color: var(--el-color-primary);
}
</style>
