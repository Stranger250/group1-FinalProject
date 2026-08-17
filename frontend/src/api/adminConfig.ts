import { request } from './request'

/** O9 模型配置（api_key 脱敏回显） */
export interface ModelConfigView {
  llm: { base_url: string; api_key_masked: string; api_key_set: boolean; model_name: string }
  vision: { base_url: string; api_key_masked: string; api_key_set: boolean; model_name: string }
}

/** O9 RAG 参数 */
export interface RagConfig {
  rag_vector_top_k: number
  rag_bm25_top_k: number
  rag_rrf_k: number
  rag_fusion_top_k: number
  rag_rerank_top_n: number
  rag_conf_refuse: number
  rag_conf_conservative: number
  rag_vec_sim_floor: number
  rag_parent_split_chars: number
  rag_child_min_chars: number
  rag_child_max_chars: number
}

export function getModelConfig() {
  return request<ModelConfigView>({ url: '/admin/config/models', method: 'GET' })
}

export function saveModelConfig(payload: Partial<Record<string, string>>) {
  return request<{ message: string } & ModelConfigView>({
    url: '/admin/config/models',
    method: 'PUT',
    data: payload,
  })
}

export function getRagConfig() {
  return request<RagConfig>({ url: '/admin/config/rag', method: 'GET' })
}

export function saveRagConfig(payload: Partial<RagConfig>) {
  return request<{ message: string; need_rebuild: boolean }>({
    url: '/admin/config/rag',
    method: 'PUT',
    data: payload,
  })
}
