"""RAG 参数聚合（对齐 docs/RAG优化方案.md §0.2 全局参数契约，唯一真源）。

代码层一律从 RAGParams 取值，不自行定义第二套参数。带 version 便于回滚/追溯。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core.config import get_settings

RAG_VERSION = "v1"


@dataclass(frozen=True)
class RAGParams:
    vector_top_k: int        # 向量路召回 Top-50
    bm25_top_k: int          # BM25 路召回 Top-50
    rrf_k: int               # RRF 融合 K=60
    fusion_top_k: int        # RRF 融合后取 Top-20 进重排
    rerank_top_n: int        # 重排后进 LLM 的父块数 Top-5
    conf_refuse: float       # 归一化置信度 < 0.30 → 拒答
    conf_conservative: float  # < 0.45 → 保守；≥ → 全量
    vec_sim_floor: float     # 向量 top-1 余弦相似度下限（< 则拒答，防无关查询幻觉）
    parent_split_chars: int  # 条长 > 该值才二次分块
    child_min_chars: int
    child_max_chars: int
    max_rounds: int          # 多轮上下文轮数
    version: str = RAG_VERSION

    @classmethod
    def from_settings(cls) -> "RAGParams":
        s = get_settings()
        return cls(
            vector_top_k=s.rag_vector_top_k,
            bm25_top_k=s.rag_bm25_top_k,
            rrf_k=s.rag_rrf_k,
            fusion_top_k=s.rag_fusion_top_k,
            rerank_top_n=s.rag_rerank_top_n,
            conf_refuse=s.rag_conf_refuse,
            conf_conservative=s.rag_conf_conservative,
            vec_sim_floor=s.rag_vec_sim_floor,
            parent_split_chars=s.rag_parent_split_chars,
            child_min_chars=s.rag_child_min_chars,
            child_max_chars=s.rag_child_max_chars,
            max_rounds=s.rag_max_rounds,
        )
