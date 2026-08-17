<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getModelConfig,
  getRagConfig,
  saveModelConfig,
  saveRagConfig,
  type RagConfig,
} from '@/api/adminConfig'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const isAdmin = ref(userStore.roleId === 3)

// ---------------- 模型配置（ADMIN） ----------------
const modelsLoading = ref(false)
const modelsSaving = ref(false)
const models = reactive({
  base_url: '',
  api_key: '',
  model_name: '',
  vision_base_url: '',
  vision_api_key: '',
  vision_model_name: '',
})

async function fetchModels() {
  modelsLoading.value = true
  try {
    const d = await getModelConfig()
    models.base_url = d.llm.base_url
    models.model_name = d.llm.model_name
    models.vision_base_url = d.vision.base_url
    models.vision_model_name = d.vision.model_name
  } catch {
    /* 错误已全局提示 */
  } finally {
    modelsLoading.value = false
  }
}

async function saveModels() {
  modelsSaving.value = true
  try {
    const res = await saveModelConfig({
      base_url: models.base_url,
      model_name: models.model_name,
      vision_base_url: models.vision_base_url,
      vision_model_name: models.vision_model_name,
      // api_key 留空 = 不修改；显式空串需单独入口（此处仅提交非空）
      ...(models.api_key.trim() ? { api_key: models.api_key.trim() } : {}),
      ...(models.vision_api_key.trim() ? { vision_api_key: models.vision_api_key.trim() } : {}),
    })
    ElMessage.success(res.message)
    models.api_key = ''
    models.vision_api_key = ''
    fetchModels()
  } catch {
    /* 错误已全局提示 */
  } finally {
    modelsSaving.value = false
  }
}

// ---------------- RAG 策略（SAFETY/ADMIN） ----------------
const ragLoading = ref(false)
const ragSaving = ref(false)
const rag = reactive<RagConfig>({
  rag_vector_top_k: 50,
  rag_bm25_top_k: 50,
  rag_rrf_k: 60,
  rag_fusion_top_k: 20,
  rag_rerank_top_n: 5,
  rag_conf_refuse: 0.3,
  rag_conf_conservative: 0.45,
  rag_vec_sim_floor: 0.75,
  rag_parent_split_chars: 400,
  rag_child_min_chars: 100,
  rag_child_max_chars: 250,
})

async function fetchRag() {
  ragLoading.value = true
  try {
    const d = await getRagConfig()
    Object.assign(rag, d)
  } catch {
    /* 错误已全局提示 */
  } finally {
    ragLoading.value = false
  }
}

async function saveRag() {
  try {
    await ElMessageBox.confirm(
      '保存后 RAG 检索参数即时生效；分块参数（父块/子块字数）需重建知识库后才对长条二次分块生效。是否保存？',
      '保存 RAG 策略',
      { type: 'warning', confirmButtonText: '保存', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  ragSaving.value = true
  try {
    const res = await saveRagConfig({ ...rag })
    ElMessage.success(res.message)
    fetchRag()
  } catch {
    /* 错误已全局提示 */
  } finally {
    ragSaving.value = false
  }
}

onMounted(() => {
  if (isAdmin.value) fetchModels()
  fetchRag()
})
</script>

<template>
  <div class="page-container">
    <!-- 模型管理（仅 ADMIN） -->
    <el-card v-if="isAdmin" shadow="never" class="cfg-card" v-loading="modelsLoading">
      <template #header>
        <div class="card-title">
          <span>模型管理（LLM / 视觉识别）</span>
          <span class="card-tip">保存后即时生效（写配置存储，重启保持）</span>
        </div>
      </template>
      <el-form label-width="120px" class="cfg-form">
        <el-divider content-position="left">大模型（问答 / 出题）</el-divider>
        <el-form-item label="Base URL">
          <el-input v-model="models.base_url" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="models.api_key"
            type="password"
            show-password
            placeholder="留空 = 保持当前密钥（已配置）"
          />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="models.model_name" placeholder="deepseek-v4-flash" />
        </el-form-item>
        <el-divider content-position="left">视觉模型（隐患图片识别）</el-divider>
        <el-form-item label="Base URL">
          <el-input v-model="models.vision_base_url" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="models.vision_api_key"
            type="password"
            show-password
            placeholder="留空 = 保持当前密钥（已配置）"
          />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="models.vision_model_name" placeholder="qwen-vl-plus" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="modelsSaving" @click="saveModels">保存模型配置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- RAG 策略（SAFETY/ADMIN） -->
    <el-card shadow="never" v-loading="ragLoading">
      <template #header>
        <div class="card-title">
          <span>RAG 检索 / 分块策略</span>
          <span class="card-tip">检索参数即时生效；分块参数需重建知识库</span>
        </div>
      </template>
      <el-form label-width="180px" class="cfg-form">
        <el-divider content-position="left">检索参数</el-divider>
        <el-form-item label="向量路召回数（vector_top_k）">
          <el-input-number v-model="rag.rag_vector_top_k" :min="10" :max="200" />
        </el-form-item>
        <el-form-item label="BM25 路召回数（bm25_top_k）">
          <el-input-number v-model="rag.rag_bm25_top_k" :min="10" :max="200" />
        </el-form-item>
        <el-form-item label="RRF 融合 K">
          <el-input-number v-model="rag.rag_rrf_k" :min="10" :max="200" />
        </el-form-item>
        <el-form-item label="融合后取前 N（fusion_top_k）">
          <el-input-number v-model="rag.rag_fusion_top_k" :min="5" :max="100" />
        </el-form-item>
        <el-form-item label="重排后进 LLM 块数（rerank_top_n）">
          <el-input-number v-model="rag.rag_rerank_top_n" :min="1" :max="20" />
        </el-form-item>
        <el-form-item label="拒答置信度阈值">
          <el-input-number v-model="rag.rag_conf_refuse" :min="0" :max="1" :step="0.05" :precision="2" />
        </el-form-item>
        <el-form-item label="保守模式阈值">
          <el-input-number v-model="rag.rag_conf_conservative" :min="0" :max="1" :step="0.05" :precision="2" />
        </el-form-item>
        <el-form-item label="向量相似度下限（拒答）">
          <el-input-number v-model="rag.rag_vec_sim_floor" :min="0" :max="1" :step="0.05" :precision="2" />
        </el-form-item>
        <el-divider content-position="left">分块参数（保存后需重建知识库生效）</el-divider>
        <el-form-item label="长条二次分块阈值（字）">
          <el-input-number v-model="rag.rag_parent_split_chars" :min="200" :max="2000" :step="50" />
        </el-form-item>
        <el-form-item label="子块最小字数">
          <el-input-number v-model="rag.rag_child_min_chars" :min="50" :max="1000" :step="10" />
        </el-form-item>
        <el-form-item label="子块最大字数">
          <el-input-number v-model="rag.rag_child_max_chars" :min="100" :max="2000" :step="10" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="ragSaving" @click="saveRag">保存 RAG 策略</el-button>
          <el-button @click="fetchRag">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.cfg-card {
  margin-bottom: 16px;
}
.card-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.card-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.cfg-form {
  max-width: 720px;
}
</style>
