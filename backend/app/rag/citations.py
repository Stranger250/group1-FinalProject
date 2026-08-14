"""回答引用组装（契约 §0.3 / §3.4：来源列表由后端从注入块组装，不由模型生成）。

n 与 prompt 注入块序号一一对应（模型只"点选" [n]）。meta/done 事件共用。
"""
from __future__ import annotations

from dataclasses import dataclass

from .rag_config import RAGParams

# 引用卡片摘要上限：父块=整条（多数条 < 400 字），截到该值即可覆盖整条正文，
# 过长条文卡片不至于过高（点卡片可查看全文）。
_SNIPPET_CHARS = 400

# 展示相关度下限：交叉引用展开块无 RRF 融合分，给非零下限，避免「被引用却显示 0%」
# 的矛盾观感。真实命中经 display_score 至少约 0.28（rank50 单路），下限不影响它们。
_DISPLAY_FLOOR = 0.05


def display_score(rrf: float, rrf_k: int, floor: float = _DISPLAY_FLOOR) -> float:
    """块级展示相关度：相对理论峰值归一化（与 retriever 置信度同口径，§0.2）。

    - 真实命中：min(1, rrf × (K+1)/2)，单路 top1≈0.50、双路 top1≈1.00、rank20≈0.38，
      内容越相关条越长，修复「相关度条永远 1%-3%」的观感问题；
    - 展开块（rrf≤0）：返回 floor 下限，语义「补入引用」。
    """
    if not rrf or rrf <= 0:
        return floor
    return round(min(1.0, rrf * (rrf_k + 1) / 2.0), 4)


@dataclass
class RetrievedBlock:
    """检索返回的块（父块粒度，含展示与落库所需全部字段）。"""
    chunk_id: str
    doc_id: str
    title: str
    doc_no: str
    category: str
    doc_level: int
    region: str
    chapter: str
    article_no: str
    content: str
    is_parent: bool
    parent_chunk_id: str
    status: str
    publish_date: str
    effective_date: str
    version: str
    source_url: str
    ref_out: list[str]
    domain_tags: list[str]
    difficulty: str
    access_level: str
    db_doc_id: int
    db_chunk_id: int
    parent_db_chunk_id: int
    # 检索过程字段
    rrf_score: float = 0.0
    confidence: float = 0.0
    mode: str = "full"
    expanded: bool = False

    def to_source(self, n: int, rrf_k: int) -> dict:
        """meta/done 引用卡片（前端先渲染"依据来源"）。

        score 为展示相关度（display_score，相对理论峰值归一化，见模块级说明），
        前端据此渲染 0-100% 的「相关度」进度条。
        """
        return {
            "n": n,
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title": self.title,
            "chapter": self.chapter,
            "article_no": self.article_no,
            "doc_no": self.doc_no,
            "effective_date": self.effective_date,
            "source_url": self.source_url,
            "snippet": self.content[:_SNIPPET_CHARS],
            "score": display_score(self.rrf_score, rrf_k),
        }


def build_citations(blocks: list[RetrievedBlock]) -> list[dict]:
    """注入块列表 → 引用列表（n 从 1 起，与 prompt [n] 对齐）。

    rrf_k 取全局 RAG 参数（K=60），用于把块级 RRF 分换算成展示相关度。
    """
    rrf_k = RAGParams.from_settings().rrf_k
    return [b.to_source(i + 1, rrf_k) for i, b in enumerate(blocks)]
