"""本地 BGE 嵌入模型封装（bge-large-zh，单例 + 线程锁）。

建库（M1）与检索（M2）共用。模型路径取 settings.embed_model_dir（绝对路径，
规避 transformers 5.14.1 相对路径误判 HuggingFace repo id 的 HFValidationError）。
BGE 系列必须 normalize_embeddings=True。
"""
from __future__ import annotations

import threading

from langchain_huggingface import HuggingFaceEmbeddings

from ..core.config import get_settings


class Embedder:
    def __init__(self) -> None:
        settings = get_settings()
        self._embeddings = HuggingFaceEmbeddings(
            model_name=settings.embed_model_dir,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self._lock = threading.Lock()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        with self._lock:
            return self._embeddings.embed_query(text)


_embedder: Embedder | None = None
_embedder_lock = threading.Lock()


def get_embedder() -> Embedder:
    """单例获取；线程安全（首次加载模型耗时，预热调用）。"""
    global _embedder
    with _embedder_lock:
        if _embedder is None:
            _embedder = Embedder()
        return _embedder
