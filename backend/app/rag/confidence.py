"""置信度归一化与三档判定（契约 §0.2：全链路唯一分制，重排分不做阈值）。

- normalize_rrf：RRF 融合分 min-max 归一化到 [0,1]（max==min 返回 0.0）；
- classify：<0.30 拒答 / 0.30-0.45 保守 / ≥0.45 全量。
阈值分布打日志，上线前按评测集（§5.6）联合标定。
"""
from __future__ import annotations


def normalize_rrf(scores: list[float]) -> list[float]:
    """min-max 归一化到 [0,1]。空列表→空；全部相等→全 0.0（无区分度）。"""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [0.0] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]


def classify(conf: float, refuse: float, conservative: float) -> str:
    if conf < refuse:
        return "refuse"
    if conf < conservative:
        return "conservative"
    return "full"
