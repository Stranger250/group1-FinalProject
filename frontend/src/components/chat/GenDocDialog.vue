<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { downloadGenDoc, previewGenDoc, type GenDocOutline } from '@/api/genDoc'

const visible = defineModel<boolean>({ required: true })

const docType = ref<'word' | 'ppt'>('word')
const topic = ref('')
const style = ref('正式')
const generating = ref(false)
const outline = ref<GenDocOutline | null>(null)
const downloading = ref(false)

const STYLE_OPTIONS = ['正式', '简明', '培训课件', '汇报演示']

async function onGenerate() {
  if (!topic.value.trim()) {
    ElMessage.warning('请输入文档主题')
    return
  }
  generating.value = true
  outline.value = null
  try {
    const res = await previewGenDoc({
      doc_type: docType.value,
      topic: topic.value.trim(),
      style: style.value,
    })
    outline.value = res.outline
  } catch {
    /* 错误已全局提示 */
  } finally {
    generating.value = false
  }
}

async function onDownload() {
  if (!outline.value) return
  downloading.value = true
  try {
    const fname = await downloadGenDoc({
      doc_type: docType.value,
      topic: topic.value.trim(),
      outline: outline.value,
    })
    ElMessage.success(`已下载：${fname}`)
  } catch (e) {
    ElMessage.error((e as Error).message || '下载失败')
  } finally {
    downloading.value = false
  }
}

function onClose() {
  visible.value = false
  outline.value = null
  topic.value = ''
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="生成文档（Word / PPT）"
    width="720px"
    destroy-on-close
    @closed="onClose"
  >
    <el-form label-width="90px">
      <el-form-item label="文档类型">
        <el-radio-group v-model="docType">
          <el-radio-button value="word">Word 文档</el-radio-button>
          <el-radio-button value="ppt">PPT 课件</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="需求描述">
        <el-input
          v-model="topic"
          type="textarea"
          :rows="3"
          maxlength="200"
          show-word-limit
          placeholder="例：隧道施工安全生产管理培训教材 / 高处作业安全培训课件 / 春节复工安全检查方案"
        />
      </el-form-item>
      <el-form-item label="风格">
        <el-select v-model="style" style="width: 200px">
          <el-option v-for="s in STYLE_OPTIONS" :key="s" :label="s" :value="s" />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="generating" @click="onGenerate">生成大纲预览</el-button>
        <el-button v-if="outline" type="success" :loading="downloading" @click="onDownload">
          <el-icon class="mr-1"><Download /></el-icon>确认并下载
        </el-button>
      </el-form-item>
    </el-form>

    <!-- 大纲预览 -->
    <div v-if="outline" class="outline-panel">
      <div class="outline-title">{{ outline.title || '文档' }}</div>
      <template v-if="docType === 'word' && outline.sections">
        <div v-for="(sec, i) in outline.sections" :key="i" class="outline-section">
          <div class="sec-heading">{{ sec.heading }}</div>
          <ul>
            <li v-for="(p, j) in sec.paragraphs" :key="j" class="sec-para">{{ p }}</li>
          </ul>
        </div>
      </template>
      <template v-else-if="docType === 'ppt' && outline.slides">
        <el-tag v-for="(s, i) in outline.slides" :key="i" size="small" effect="plain" class="slide-tag">
          {{ s.title }}
        </el-tag>
        <div class="slide-count">共 {{ outline.slides.length }} 页</div>
      </template>
    </div>
  </el-dialog>
</template>

<style scoped>
.outline-panel {
  max-height: 380px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 16px;
  background-color: var(--el-bg-color-page);
}
.outline-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 10px;
}
.outline-section {
  margin-bottom: 10px;
}
.sec-heading {
  font-weight: 600;
  color: var(--el-color-primary);
  margin-bottom: 4px;
}
.sec-para {
  font-size: 13px;
  line-height: 1.7;
  margin-left: -16px;
}
.slide-tag {
  margin: 0 6px 6px 0;
}
.slide-count {
  margin-top: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.mr-1 {
  margin-right: 4px;
}
</style>
