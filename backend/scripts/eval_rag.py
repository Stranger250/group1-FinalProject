# -*- coding: utf-8 -*-
"""O6 RAG 评测：100 条测试 query（50 条 1对1 / 33 条 1对2 / 17 条 1对3）。

用法：cd backend && python scripts/eval_rag.py [--queries data/eval/queries_v1.json] [--top-k 5] [--save baseline_v1.json]
输出：
  1) 逐条检索效果（召回块清单 + 命中判定 + 依据预览，供人工抽查）；
  2) 分组指标：Recall@K / 块命中率 / MRR / NDCG@K；
  3) baseline_v1.json 存档（git 可追溯，标记 RAG v1.0）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.rag.retriever import get_retriever  # noqa: E402


def match_block(block, doc_title: str, kw: str) -> bool:
    """块命中判定：title 含文档标题且 content 含关键词。"""
    title = block.title or ""
    content = block.content or ""
    return doc_title in title and kw in content


def eval_query(retriever, item: dict, top_k: int) -> dict:
    """单条 query 评测：返回召回明细与指标原始量。"""
    query = item["query"]
    expect = item["expect"]
    result = retriever.search(query)
    blocks = result.blocks[:top_k]

    # 期望元组 → 是否在 top-K 中命中 + 所在排名（1-based；未命中 None）
    matched: list[dict] = []
    for i, (doc_title, kw) in enumerate(expect):
        rank = None
        for idx, b in enumerate(blocks, start=1):
            if match_block(b, doc_title, kw):
                rank = idx
                break
        matched.append({"doc": doc_title, "kw": kw, "rank": rank})

    # MRR：首个命中期望项的最小排名倒数
    ranks = [m["rank"] for m in matched if m["rank"] is not None]
    mrr = 1.0 / min(ranks) if ranks else 0.0
    # Recall@K：命中期望项占比
    recall = len(ranks) / len(expect) if expect else 0.0
    # NDCG@K（rank 折扣；理想排序 = 前 len(expect) 位全命中）
    dcg = sum(1.0 / _log2(rank + 1) for rank in ranks)
    ideal_ranks = list(range(1, min(len(expect), top_k) + 1))
    idcg = sum(1.0 / _log2(r + 1) for r in ideal_ranks)
    ndcg = dcg / idcg if idcg else 0.0

    return {
        "id": item["id"],
        "query": query,
        "group_size": len(expect),
        "recall": recall,
        "mrr": mrr,
        "ndcg": ndcg,
        "matched": matched,
        "blocks": [
            {"rank": i, "chunk_id": b.chunk_id, "title": b.title,
             "article_no": b.article_no, "content": (b.content or "")[:60]}
            for i, b in enumerate(blocks, start=1)
        ],
    }


def _log2(x: float) -> float:
    import math
    return math.log2(x) if x > 0 else 1.0


def main() -> int:
    ap = argparse.ArgumentParser(description="O6 RAG 评测（单变量优化实验框架）")
    ap.add_argument("--queries", default=str(BACKEND_DIR / "data" / "eval" / "queries_v1.json"))
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--save", default=str(BACKEND_DIR / "data" / "eval" / "baseline_v1.json"))
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="单变量覆盖 settings（如 --set rag_rrf_k=40），实验用不改代码")
    ap.add_argument("--tag", default="", help="实验标签，写入存档备注")
    args = ap.parse_args()

    # 单变量覆盖（仅本次进程生效；retriever 单例在覆盖后构建）
    from app.core.config import get_settings as _gs
    _s = _gs()
    for kv in args.set:
        key, _, value = kv.partition("=")
        if not hasattr(_s, key):
            print(f"!! 未知配置键: {key}")
            return 2
        try:
            cur = getattr(_s, key)
            setattr(_s, key, type(cur)(value))
        except (TypeError, ValueError):
            setattr(_s, key, value)
        print(f"[实验覆盖] {key} = {getattr(_s, key)}")
    _gs.cache_clear()

    with open(args.queries, encoding="utf-8") as f:
        data = json.load(f)
    retriever = get_retriever()
    top_k = args.top_k

    results: dict[str, list[dict]] = {}
    print("=" * 80)
    for group, items in data["groups"].items():
        results[group] = []
        print(f"\n[组 {group}] {len(items)} 条 query")
        for item in items:
            r = eval_query(retriever, item, top_k)
            results[group].append(r)
            hit = f"{r['recall']:.0%} MRR={r['mrr']:.3f}"
            print(f"  {r['id']} [{hit}] {r['query']}")
            for m in r["matched"]:
                mark = "✓" if m["rank"] else "✗"
                print(f"      {mark} 期望: {m['doc']} / {m['kw']}" + (f" → rank {m['rank']}" if m["rank"] else ""))
            print(f"      召回: " + " | ".join(f"#{b['rank']}{b['title']} {b['article_no']}" for b in r["blocks"]))

    # ---------- 汇总指标 ----------
    print("\n" + "=" * 80)
    print(f"== 汇总（top_k={top_k}）==")
    agg = {"overall": {"n": 0, "recall": 0.0, "mrr": 0.0, "ndcg": 0.0}}
    for group, items in results.items():
        n = len(items)
        rec = sum(r["recall"] for r in items) / n
        mrr = sum(r["mrr"] for r in items) / n
        ndcg = sum(r["ndcg"] for r in items) / n
        agg[group] = {"n": n, "recall": rec, "mrr": mrr, "ndcg": ndcg}
        agg["overall"]["n"] += n
        agg["overall"]["recall"] += sum(r["recall"] for r in items)
        agg["overall"]["mrr"] += sum(r["mrr"] for r in items)
        agg["overall"]["ndcg"] += sum(r["ndcg"] for r in items)
        print(f"  {group:<8} n={n:<4} Recall@{top_k}={rec:.3f}  MRR={mrr:.3f}  NDCG@{top_k}={ndcg:.3f}")
    o = agg["overall"]
    o["recall"] /= o["n"]
    o["mrr"] /= o["n"]
    o["ndcg"] /= o["n"]
    print(f"  overall  n={o['n']:<4} Recall@{top_k}={o['recall']:.3f}  MRR={o['mrr']:.3f}  NDCG@{top_k}={o['ndcg']:.3f}")

    # ---------- 存档 ----------
    from app.core.config import get_settings
    settings = get_settings()
    baseline = {
        "version": "baseline_v1",
        "rag_version": "v1.0",
        "tag": args.tag or "baseline",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "overrides": dict(kv.split("=", 1) for kv in args.set),
        "queries_file": os.path.basename(args.queries),
        "top_k": top_k,
        "config": {
            "rag_vector_top_k": settings.rag_vector_top_k,
            "rag_bm25_top_k": settings.rag_bm25_top_k,
            "rag_rrf_k": settings.rag_rrf_k,
            "rag_fusion_top_k": settings.rag_fusion_top_k,
            "rag_rerank_top_n": settings.rag_rerank_top_n,
            "rag_parent_split_chars": settings.rag_parent_split_chars,
            "rag_child_min_chars": settings.rag_child_min_chars,
            "rag_child_max_chars": settings.rag_child_max_chars,
        },
        "metrics": {k: {kk: round(vv, 4) for kk, vv in v.items() if isinstance(vv, (int, float))} for k, v in agg.items()},
        "details": {g: [{"id": r["id"], "recall": round(r["recall"], 3), "mrr": round(r["mrr"], 3)} for r in items]
                    for g, items in results.items()},
    }
    save_path = Path(args.save)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已存档: {save_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
