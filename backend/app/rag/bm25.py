"""BM25 关键词检索：jieba 精确模式分词 + rank_bm25（RAG 方案 §2.2）。

条文有大量精确术语（条号/期限/金额），BM25 负责字面命中。索引从 Chroma 全量文档一次性构建，
单一数据源（不重建）；在线 get_scores 用线程锁（rank_bm25 非线程安全）。
"""
from __future__ import annotations

import threading

import jieba
from rank_bm25 import BM25Okapi


class BM25Index:
    def __init__(self, docs: list[dict], access_by_id: dict[str, str] | None = None):
        """docs: [{chunk_id, content}]；access_by_id: chunk_id → access_level（可选过滤）。"""
        self._access = access_by_id or {}
        self._tokenized = [list(jieba.cut(d["content"], cut_all=False)) for d in docs]
        self._bm25 = BM25Okapi(self._tokenized)
        self._ids = [d["chunk_id"] for d in docs]
        self._lock = threading.Lock()
        # 预热 jieba 词典（首次 cut 会建索引，避免在线首查卡顿）
        jieba.initialize()

    def search(self, query: str, top_k: int, access_levels: tuple[str, ...] = ("公开",)) -> list[tuple[str, float]]:
        """返回 [(chunk_id, bm25_score)] 降序，仅含 score>0 且权限可见。"""
        tokens = list(jieba.cut(query, cut_all=False))
        if not tokens:
            return []
        with self._lock:
            scores = self._bm25.get_scores(tokens)
        ranked = sorted(zip(self._ids, scores), key=lambda x: x[1], reverse=True)
        out: list[tuple[str, float]] = []
        for cid, sc in ranked:
            if sc <= 0:
                break  # 已降序，后续全 ≤0
            if access_levels and self._access.get(cid) not in access_levels:
                continue
            out.append((cid, float(sc)))
            if len(out) >= top_k:
                break
        return out
