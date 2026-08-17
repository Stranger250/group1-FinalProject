<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteDocument,
  getDocument,
  listDocuments,
  setDocumentStatus,
  uploadDocument,
  type KnowledgeDoc,
  type KnowledgeDocDetail,
} from '@/api/document'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const isManager = ref(userStore.roleId === 2 || userStore.roleId === 3)

// ---------------- 列表 ----------------
const loading = ref(false)
const list = ref<KnowledgeDoc[]>([])
const total = ref(0)
const query = reactive({
  doc_type: '',
  tier: '',
  keyword: '',
  page: 1,
  page_size: 20,
})

const TYPE_OPTIONS = [
  { label: '法律', value: 'law' },
  { label: '法规', value: 'regulation' },
  { label: '企业制度', value: 'company' },
  { label: '操作规程', value: 'sop' },
  { label: '预案', value: 'plan' },
  { label: '案例', value: 'case' },
]
const TIER_OPTIONS = [
  { label: '国家级', value: 'national' },
  { label: '省级', value: 'province' },
  { label: '更低级', value: 'lower' },
]
const STATUS_MAP: Record<string, { label: string; tag: string }> = {
  SUCCESS: { label: '生效', tag: 'success' },
  DISABLED: { label: '已停用', tag: 'info' },
  PENDING: { label: '解析中', tag: 'warning' },
  FAILED: { label: '失败', tag: 'danger' },
}

async function fetchList() {
  loading.value = true
  try {
    const data = await listDocuments({
      doc_type: query.doc_type || undefined,
      tier: query.tier || undefined,
      keyword: query.keyword || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    list.value = data.items
    total.value = data.total
  } catch {
    /* 错误已全局提示 */
  } finally {
    loading.value = false
  }
}

function onSearch() {
  query.page = 1
  fetchList()
}

function onReset() {
  query.doc_type = ''
  query.tier = ''
  query.keyword = ''
  query.page = 1
  fetchList()
}

// ---------------- 详情 ----------------
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<KnowledgeDocDetail | null>(null)

async function openDetail(row: KnowledgeDoc) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getDocument(row.id)
  } catch {
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

// ---------------- 管理端：上传 ----------------
const uploadVisible = ref(false)
const uploading = ref(false)
const uploadForm = reactive({
  file: null as File | null,
  title: '',
  doc_type: 'law',
  doc_level: 1,
  region: '',
  source_url: '',
})

function pickUploadFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const f = input.files?.[0]
  if (!f) return
  const okExt = /\.(txt|md|pdf|docx)$/i.test(f.name)
  if (!okExt) {
    ElMessage.error('仅支持 txt/md/pdf/docx 文档')
    return
  }
  if (f.size > 10 * 1024 * 1024) {
    ElMessage.error('文档超过大小上限（10MB）')
    return
  }
  uploadForm.file = f
  if (!uploadForm.title) uploadForm.title = f.name.replace(/\.(txt|md|pdf|docx)$/i, '')
}

async function submitUpload() {
  if (!uploadForm.file) {
    ElMessage.warning('请先选择文档文件')
    return
  }
  uploading.value = true
  try {
    const res = await uploadDocument({
      file: uploadForm.file,
      title: uploadForm.title || undefined,
      doc_type: uploadForm.doc_type,
      doc_level: uploadForm.doc_level,
      region: uploadForm.region || undefined,
      source_url: uploadForm.source_url || undefined,
    })
    ElMessage.success(`《${res.title}》入库成功（${res.blocks} 块 / 新增 ${res.added_chunks}）`)
    uploadVisible.value = false
    uploadForm.file = null
    fetchList()
  } catch {
    /* 错误已全局提示 */
  } finally {
    uploading.value = false
  }
}

// ---------------- 管理端：停用/启用/删除 ----------------
async function onToggleStatus(row: KnowledgeDoc) {
  const target = row.status === 'DISABLED' ? 'SUCCESS' : 'DISABLED'
  const action = row.status === 'DISABLED' ? '启用' : '停用'
  try {
    await ElMessageBox.confirm(`确定${action}文档《${row.name}》？`, `${action}确认`, {
      type: 'warning',
      confirmButtonText: action,
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await setDocumentStatus(row.id, target as 'DISABLED' | 'SUCCESS')
    ElMessage.success(`已${action}`)
    fetchList()
  } catch {
    /* 错误已全局提示 */
  }
}

async function onDelete(row: KnowledgeDoc) {
  try {
    await ElMessageBox.confirm(
      `确定删除文档《${row.name}》？删除后其 ${row.chunk_count} 个分块将同步移除，检索不再命中。`,
      '删除确认',
      { type: 'error', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const res = await deleteDocument(row.id)
    ElMessage.success(`已删除（移除 ${res.deleted_chunks} 个分块）`)
    fetchList()
  } catch {
    /* 错误已全局提示 */
  }
}

function fmtChars(n: number) {
  if (n >= 10000) return `${(n / 10000).toFixed(1)} 万字`
  return `${n} 字`
}

onMounted(fetchList)
</script>

<template>
  <div class="doc-library">
    <div class="page-header">
      <div>
        <h2>法规文档库</h2>
        <p class="page-desc">蜀道安全助手知识库全部法规、制度、规程、预案与事故案例（共 {{ total }} 篇）</p>
      </div>
      <el-button v-if="isManager" type="primary" @click="uploadVisible = true">
        <el-icon class="mr-1"><Upload /></el-icon>添加文档
      </el-button>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select v-model="query.doc_type" placeholder="文档类型" clearable style="width: 150px" @change="onSearch">
        <el-option v-for="t in TYPE_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-select v-model="query.tier" placeholder="行政层级" clearable style="width: 140px" @change="onSearch">
        <el-option v-for="t in TIER_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-input
        v-model="query.keyword"
        placeholder="文档名关键字"
        clearable
        style="width: 220px"
        @keyup.enter="onSearch"
        @clear="onSearch"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="onReset">重置</el-button>
    </div>

    <!-- 列表 -->
    <el-table v-loading="loading" :data="list" stripe style="width: 100%" @row-click="openDetail">
      <el-table-column prop="name" label="文档名称" min-width="280" show-overflow-tooltip />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.doc_type_label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="层级" width="90">
        <template #default="{ row }">
          {{ row.tier === 'national' ? '国家级' : row.tier === 'province' ? '省级' : '更低级' }}
        </template>
      </el-table-column>
      <el-table-column prop="article_count" label="条数" width="80" />
      <el-table-column label="字数" width="100">
        <template #default="{ row }">{{ fmtChars(row.char_count) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="(STATUS_MAP[row.status]?.tag as any) ?? 'info'">
            {{ STATUS_MAP[row.status]?.label ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上传时间" width="170">
        <template #default="{ row }">{{ row.create_time?.slice(0, 16) ?? '-' }}</template>
      </el-table-column>
      <el-table-column v-if="isManager" label="操作" width="170" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click.stop="openDetail(row)">预览</el-button>
          <el-button link :type="row.status === 'DISABLED' ? 'success' : 'warning'" size="small" @click.stop="onToggleStatus(row)">
            {{ row.status === 'DISABLED' ? '启用' : '停用' }}
          </el-button>
          <el-button link type="danger" size="small" @click.stop="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.page_size"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @current-change="fetchList"
        @size-change="onSearch"
      />
    </div>

    <!-- 详情预览抽屉 -->
    <el-drawer v-model="detailVisible" size="55%" :title="detail?.name ?? '文档详情'" destroy-on-close>
      <div v-loading="detailLoading">
        <template v-if="detail">
          <el-descriptions :column="3" border size="small" class="detail-meta">
            <el-descriptions-item label="类型">{{ detail.doc_type_label }}</el-descriptions-item>
            <el-descriptions-item label="层级">
              {{ detail.tier === 'national' ? '国家级' : detail.tier === 'province' ? '省级' : '更低级' }}
            </el-descriptions-item>
            <el-descriptions-item label="区域">{{ detail.region || '-' }}</el-descriptions-item>
            <el-descriptions-item label="条数">{{ detail.article_count }}</el-descriptions-item>
            <el-descriptions-item label="字数">{{ fmtChars(detail.char_count) }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag size="small" :type="(STATUS_MAP[detail.status]?.tag as any) ?? 'info'">
                {{ STATUS_MAP[detail.status]?.label ?? detail.status }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
          <div v-if="detail.source_url" class="detail-source">
            来源：<el-link type="primary" :href="detail.source_url" target="_blank" rel="noopener">{{ detail.source_url }}</el-link>
          </div>

          <el-collapse class="detail-chapters">
            <el-collapse-item v-for="(ch, i) in detail.chapters" :key="i" :title="`${ch.chapter}（${ch.articles.length} 条）`">
              <div v-for="(a, j) in ch.articles" :key="j" class="article-item">
                <div v-if="a.article_no" class="article-no">{{ a.article_no }}</div>
                <div class="article-content">{{ a.content }}</div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </template>
      </div>
    </el-drawer>

    <!-- 管理端：添加文档 -->
    <el-dialog v-model="uploadVisible" title="添加文档（入库即检索）" width="560px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="文档文件" required>
          <input type="file" accept=".txt,.md,.pdf,.docx" class="file-input" @change="pickUploadFile" />
          <div v-if="uploadForm.file" class="file-name">{{ uploadForm.file.name }}</div>
        </el-form-item>
        <el-form-item label="文档标题">
          <el-input v-model="uploadForm.title" placeholder="缺省用文件名（不含扩展名）" />
        </el-form-item>
        <el-form-item label="文档类型" required>
          <el-select v-model="uploadForm.doc_type" style="width: 100%">
            <el-option v-for="t in TYPE_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="行政层级">
          <el-input-number v-model="uploadForm.doc_level" :min="1" :max="5" />
          <span class="level-hint">1 法律 / 2 行政法规 / 3 部门规章 / 4 地方规章 / 5 更低级</span>
        </el-form-item>
        <el-form-item label="区域">
          <el-input v-model="uploadForm.region" placeholder="如：四川 / 国家" />
        </el-form-item>
        <el-form-item label="来源链接">
          <el-input v-model="uploadForm.source_url" placeholder="原文出处 URL（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitUpload">上传入库</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.doc-library {
  padding: 16px 20px;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 14px;
}
.page-header h2 {
  margin: 0 0 4px;
}
.page-desc {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
.mr-1 {
  margin-right: 4px;
}
.detail-meta {
  margin-bottom: 12px;
}
.detail-source {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
  word-break: break-all;
}
.article-item {
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.article-no {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-color-primary);
  margin-bottom: 2px;
}
.article-content {
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
}
.file-input {
  font-size: 13px;
}
.file-name {
  margin-top: 6px;
  font-size: 13px;
  color: var(--el-color-primary);
}
.level-hint {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
