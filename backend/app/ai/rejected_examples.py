"""负样本回流（_drafts/4-AI出题专项 §5「负样本回流闭环」落地）。

设计：
- 审核驳回（REJECT）时，把题面 + 驳回意见写入 backend/data/rejected_examples.json；
- 出题（generate）时加载最近 N 条反例，注入出题 prompt 作为「需规避的错误模式」；
- 反例文件为 JSON 数组，上限截断（默认保留最近 200 条），写入失败仅告警不阻断审核。

与既有 review_note（库内留痕）的关系：review_note 是单题驳回记录（库内）；
反例库是跨题复用的「出题约束输入」，二者互补。
"""
from __future__ import annotations

import json
import logging
import threading
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("gen_service.rejected")

# backend/data/rejected_examples.json：config.py 位于 backend/app/core，父级两级 = backend；
# 容器部署用 DATA_DIR 环境变量指定（compose 挂载 /data）
import os as _os
_DATA_DIR = Path(_os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
_REJECTED_FILE = _DATA_DIR / "rejected_examples.json"

# 反例库上限：超出截断（保留最近 _MAX_EXAMPLES 条）
_MAX_EXAMPLES = 200

# 出题时注入 prompt 的最近反例条数
_RECENT_FOR_PROMPT = 10

_lock = threading.Lock()


def _load_list() -> list[dict]:
    """读反例文件；不存在/损坏返回空列表。"""
    if not _REJECTED_FILE.exists():
        return []
    try:
        data = json.loads(_REJECTED_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        logger.warning("反例库读取失败，按空处理：%s", _REJECTED_FILE)
        return []


def add_rejected_example(*, content: str, type_: str, knowledge_point: str,
                         review_note: str) -> None:
    """追加一条驳回反例（题面 + 驳回意见），截断到上限。失败仅告警。"""
    try:
        with _lock:
            items = _load_list()
            items.append(
                {
                    "content": (content or "")[:200],
                    "type": type_,
                    "knowledge_point": (knowledge_point or "")[:64],
                    "review_note": (review_note or "")[:200],
                }
            )
            # 保留最近 _MAX_EXAMPLES 条
            if len(items) > _MAX_EXAMPLES:
                items = items[-_MAX_EXAMPLES:]
            _REJECTED_FILE.parent.mkdir(parents=True, exist_ok=True)
            _REJECTED_FILE.write_text(
                json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8"
            )
    except Exception:  # noqa: BLE001 —— 反例写入失败不阻断审核
        logger.exception("反例库写入失败")


def load_recent_examples(limit: int = _RECENT_FOR_PROMPT) -> list[dict]:
    """取最近 limit 条反例（供出题 prompt 注入）。"""
    with _lock:
        items = _load_list()
    return items[-limit:]
