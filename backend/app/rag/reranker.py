"""bge-reranker-base cross-encoder 精排（RAG 方案 §2.4：Top-20 → Top-5）。

对法条细节差异敏感（30 日 vs 15 日、部门 A vs B），弥补 bi-encoder 的钝感。
重排分只做相对排序，绝对阈值走归一化置信度（契约 §0.2）。
模型路径绝对（规避 transformers 5.14.1 相对路径 HFValidationError），单例 + 线程锁。
"""
from __future__ import annotations

import threading

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from ..core.config import get_settings


class LocalReranker:
    def __init__(self) -> None:
        path = get_settings().rerank_model_dir
        self._tokenizer = AutoTokenizer.from_pretrained(path)
        self._model = AutoModelForSequenceClassification.from_pretrained(path)
        self._model.eval()
        self._lock = threading.Lock()

    def rerank(self, query: str, pairs: list[tuple[str, str]], top_n: int) -> list[tuple[str, str, float]]:
        """pairs = [(chunk_id, text)]；返回 [(chunk_id, text, score)] 降序前 top_n。"""
        if not pairs:
            return []
        texts = [p[1] for p in pairs]
        inputs = self._tokenizer(
            [[query, t] for t in texts], padding=True, truncation=True,
            max_length=512, return_tensors="pt",
        )
        with self._lock, torch.no_grad():
            logits = self._model(**inputs).logits.view(-1).float().tolist()
        ranked = sorted(
            [(pairs[i][0], texts[i], logits[i]) for i in range(len(pairs))],
            key=lambda x: x[2], reverse=True,
        )
        return ranked[:top_n]


_reranker: LocalReranker | None = None
_reranker_lock = threading.Lock()


def get_reranker() -> LocalReranker:
    """单例；首次加载模型耗时，由 main.py lifespan 预热。"""
    global _reranker
    with _reranker_lock:
        if _reranker is None:
            _reranker = LocalReranker()
        return _reranker
