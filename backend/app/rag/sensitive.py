"""敏感词过滤（RAG 方案 §3.8：入口预检，命中即拦截不进检索/LLM）。

词库：backend/data/sensitive_words.txt（每行一个词，# 注释/空行忽略），启动时一次性载入。
MVP 用包含检查（词库小）；词库扩大后可换 DFA。返回命中的敏感词列表（空 = 放行）。
"""
from __future__ import annotations

import os
import threading
from functools import lru_cache
from pathlib import Path

# backend/data/sensitive_words.txt：config.py 位于 backend/app/core，父级两级 = backend；
# 容器部署时用环境变量 DATA_DIR 指定（compose 挂载 /data），兼容两种环境。
_DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
_SENSITIVE_FILE = _DATA_DIR / "sensitive_words.txt"


def _read_words(path: Path) -> list[str]:
    if not path.exists():
        return []
    words: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        w = line.strip()
        if not w or w.startswith("#"):
            continue
        words.append(w)
    return words


@lru_cache(maxsize=1)
def load_sensitive_words() -> tuple[str, ...]:
    return tuple(_read_words(_SENSITIVE_FILE))


def contains_sensitive(text: str, words: tuple[str, ...] | None = None) -> list[str]:
    """返回 text 中命中的敏感词列表；词库为空恒返回 []。"""
    if words is None:
        words = load_sensitive_words()
    if not words or not text:
        return []
    return [w for w in words if w in text]
