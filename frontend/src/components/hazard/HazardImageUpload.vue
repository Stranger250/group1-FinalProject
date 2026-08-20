<!-- 隐患图片多图上传（≤9 张）：先前端校验 → uploadHazardImage 拿 URL → v-model 回传 URL 列表。
     通过 defineExpose 暴露 getFileByUrl(url)，供父级「AI 识别」复用原始 File。 -->
<template>
  <div class="hazard-image-upload">
    <div v-if="modelValue.length" class="thumb-list">
      <div v-for="(url, idx) in modelValue" :key="url" class="thumb-item">
        <el-image
          class="thumb-img"
          :src="url"
          fit="contain"
          :preview-src-list="modelValue"
          :initial-index="idx"
          preview-teleported
        />
        <el-icon class="del-btn" title="删除" @click.stop="removeAt(idx)"><Delete /></el-icon>
        <span class="thumb-order">{{ idx + 1 }}</span>
      </div>
    </div>

    <el-upload
      v-if="modelValue.length < max"
      class="upload-trigger"
      :show-file-list="false"
      :accept="'.jpg,.jpeg,.png'"
      :multiple="true"
      :disabled="uploading"
      :http-request="doUpload"
      :before-upload="beforeUpload"
    >
      <div class="upload-btn" :class="{ loading: uploading }">
        <el-icon v-if="!uploading" class="el-icon--upload"><Plus /></el-icon>
        <el-icon v-else class="is-loading"><Loading /></el-icon>
        <div class="upload-text">{{ uploading ? '上传中…' : '点击上传' }}</div>
        <div class="upload-tip">jpg/png/jpeg，≤5MB，最多 {{ max }} 张</div>
      </div>
    </el-upload>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import { uploadHazardImage } from '@/api/hazard'
import { validateImage } from '@/utils/validate'

const props = withDefaults(
  defineProps<{ modelValue: string[]; max?: number; files?: Map<string, File> }>(),
  { max: 9 },
)
const emit = defineEmits<{ (e: 'update:modelValue', value: string[]): void }>()

const uploadingCount = ref(0)
const uploading = computed(() => uploadingCount.value > 0)

/** url → 原始 File 映射（AI 识别复用时按 url 反查），非响应式内部表。
    传入了 files prop 则使用外部共享表（跨页面持久化场景），否则用组件内部表。 */
const fileMap = new Map<string, File>()

function activeMap(): Map<string, File> {
  return props.files ?? fileMap
}

/** 选择文件后立即校验（返回 false 阻断上传，不调接口） */
function beforeUpload(raw: File) {
  const err = validateImage(raw)
  if (err) {
    ElMessage.warning(err)
    return false
  }
  return true
}

/** 构造 el-upload onError 需要的 UploadAjaxError 形状错误 */
function uploadAjaxError(message: string) {
  return Object.assign(new Error(message), {
    name: 'UploadAjaxError',
    status: 0,
    method: 'POST',
    url: '',
  })
}

/** 自定义上传：校验 → uploadHazardImage → 拿 {url} 追加进 v-model */
async function doUpload(options: UploadRequestOptions) {
  const raw = options.file
  const err = validateImage(raw)
  if (err) {
    ElMessage.warning(err)
    options.onError(uploadAjaxError(err))
    return
  }
  if (props.modelValue.length >= props.max) {
    ElMessage.warning(`最多上传 ${props.max} 张图片`)
    options.onError(uploadAjaxError('超出数量上限'))
    return
  }
  uploadingCount.value++
  try {
    const res = await uploadHazardImage(raw)
    if (res.code === 200) {
      activeMap().set(res.data.url, raw)
      emit('update:modelValue', [...props.modelValue, res.data.url])
      options.onSuccess(res)
      ElMessage.success('图片上传成功')
    } else {
      ElMessage.error(res.message || '图片上传失败')
      options.onError(uploadAjaxError(res.message || '上传失败'))
    }
  } catch (e) {
    // HTTP 层错误（含 503 视觉/存储降级）由 request 拦截器统一提示；此处补可跳过引导
    const status = (e as { response?: { status?: number } })?.response?.status
    if (status === 503) ElMessage.warning('图片上传服务暂不可用，可稍后重试或跳过该图片')
    const msg = e instanceof Error ? e.message : '上传失败'
    options.onError(uploadAjaxError(msg))
  } finally {
    uploadingCount.value--
  }
}

function removeAt(idx: number) {
  const list = [...props.modelValue]
  const [removed] = list.splice(idx, 1)
  if (removed) activeMap().delete(removed)
  emit('update:modelValue', list)
}

/** 父级 AI 识别复用：按 URL 取回原始 File */
function getFileByUrl(url: string): File | undefined {
  return activeMap().get(url)
}

defineExpose({ getFileByUrl })
</script>

<style scoped>
.hazard-image-upload {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.thumb-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.thumb-item {
  position: relative;
  width: 104px;
  height: 104px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-light, #e5e1d7);
  background: #2b2f33; /* 深色底衬托 contain 图片，避免白边混淆 */
}

.thumb-img {
  width: 100%;
  height: 100%;
  display: block;
  cursor: zoom-in;
}

.del-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  border-radius: 4px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
}

.thumb-item:hover .del-btn {
  opacity: 1;
}

.thumb-order {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  font-size: 12px;
  color: #fff;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 4px;
}

.upload-trigger {
  display: inline-flex;
}

.upload-btn {
  width: 104px;
  height: 104px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border: 1px dashed var(--el-border-color-dark, #c5bfb1);
  border-radius: 6px;
  color: var(--el-text-color-secondary, #707a78);
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}

.upload-btn:hover {
  border-color: var(--el-color-primary, #1e5a52);
  color: var(--el-color-primary, #1e5a52);
}

.upload-btn.loading {
  cursor: not-allowed;
  opacity: 0.7;
}

.upload-text {
  font-size: 13px;
}

.upload-tip {
  font-size: 11px;
  color: #b0b6bf;
  padding: 0 6px;
  text-align: center;
}
</style>
