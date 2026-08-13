"""回答引用组装（契约 §0.3 / §3.4：来源列表由后端从注入块组装，不由模型生成）。

n 与 prompt 注入块序号一一对应（模型只"点选" [n]）。meta/done 事件共用。
"""
from __future__ import annotations

from dataclasses import dataclass


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

    def to_source(self, n: int) -> dict:
        """meta/done 引用卡片（前端先渲染"依据来源"）。"""
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
            "snippet": self.content[:120],
        }


def build_citations(blocks: list[RetrievedBlock]) -> list[dict]:
    """注入块列表 → 引用列表（n 从 1 起，与 prompt [n] 对齐）。"""
    return [b.to_source(i + 1) for i, b in enumerate(blocks)]
