# -*- coding: utf-8 -*-
"""O4 六类语料生成器：企业安全管理制度 / 安全操作规程 / 应急预案 / 典型事故案例分析。

用法：cd backend && python scripts/gen_six_category_corpus.py
输出：
  1) 新增四类语料 JSON 写入 ../crawler_output/{标题}.json（统一 schema，含 doc_type）；
  2) 为既有 28 部法规 JSON 幂等补 doc_type 字段（法律→law，其余→regulation）；
  3) 打印按 doc_type 分组的统计（文件数/条数），供 O4 验收。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BACKEND_DIR.parent / "crawler_output"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_data import case_data, company_data, plan_data, sop_data  # noqa: E402

# 六类 doc_type 与 category 标签
DOC_TYPE_LABEL = {
    "law": "法律",
    "regulation": "行政法规",
    "company": "企业规范",
    "sop": "安全操作规程",
    "plan": "应急预案",
    "case": "典型事故案例",
}

# 既有 28 部法规中属于「法律」的标题（其余归 regulation）
LAW_TITLES = {
    "中华人民共和国安全生产法", "中华人民共和国消防法", "中华人民共和国建筑法",
    "中华人民共和国突发事件应对法", "中华人民共和国职业病防治法", "中华人民共和国行政处罚法",
    "中华人民共和国行政强制法", "中华人民共和国道路交通安全法", "中华人民共和国公路法",
}

_CHAPTER_CN = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十")


def _num_cn(n: int) -> str:
    if n <= 10:
        return _CHAPTER_CN[n - 1]
    return str(n)


def build_doc(title: str, doc_type: str, chapters: list[tuple[str, list[str]]],
              category: str, region: str, source: str, publish_date: str,
              doc_level: int = 3, doc_no: str = "", source_url: str = "") -> dict:
    """章节元组列表 → 统一 schema JSON。条号自动编号（第一条…）。"""
    out_chapters = []
    article_seq = 0
    for ci, (ch_name, items) in enumerate(chapters, start=1):
        arts = []
        for content in items:
            article_seq += 1
            arts.append({"no": f"第{_num_cn(article_seq)}条", "content": content})
        out_chapters.append({"chapter": f"第{_num_cn(ci)}章 {ch_name}", "articles": arts})
    return {
        "title": title,
        "doc_no": doc_no,
        "category": category,
        "doc_type": doc_type,
        "doc_level": doc_level,
        "region": region,
        "source": source,
        "source_url": source_url,
        "publish_date": publish_date,
        "effective_date": publish_date,
        "status": "现行有效",
        "chapters": out_chapters,
    }


def count_articles(doc: dict) -> int:
    return sum(len(ch["articles"]) for ch in doc.get("chapters") or [])


def gen_new_docs() -> list[dict]:
    """四类新语料 → 文档列表。"""
    docs: list[dict] = []

    for title, custom in company_data.COMPANY_DOCS:
        docs.append(build_doc(
            title, "company", company_data.build_chapters(custom),
            DOC_TYPE_LABEL["company"], "国家", "企业安全管理制度汇编", "2024-01-01",
            doc_level=2,
        ))
    for title, custom in sop_data.SOP_DOCS:
        docs.append(build_doc(
            title, "sop", sop_data.build_chapters(custom),
            DOC_TYPE_LABEL["sop"], "国家", "企业安全操作规程汇编", "2024-01-01",
            doc_level=2,
        ))
    for title, custom in plan_data.PLAN_DOCS:
        docs.append(build_doc(
            title, "plan", plan_data.build_chapters(custom),
            DOC_TYPE_LABEL["plan"], "国家", "企业应急预案体系", "2024-01-01",
            doc_level=2,
        ))
    for title, custom in case_data.CASE_DOCS:
        docs.append(build_doc(
            title, "case", case_data.build_chapters(custom),
            DOC_TYPE_LABEL["case"], "国家", "典型事故案例分析汇编", "2024-01-01",
            doc_level=2,
        ))
    return docs


def patch_existing_docs() -> tuple[int, int]:
    """给既有法规 JSON 幂等补 doc_type（law/regulation）。返回 (文件数, 条数)。"""
    patched = 0
    total_articles = 0
    for p in sorted(OUTPUT_DIR.glob("*.json")):
        if p.name == "index.json" or p.name.startswith("_"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or "title" not in data:
            continue
        total_articles += sum(len(ch.get("articles") or []) for ch in data.get("chapters") or [])
        if "doc_type" in data:
            continue  # 已打标，跳过
        data["doc_type"] = "law" if data["title"] in LAW_TITLES else "regulation"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        patched += 1
    return patched, total_articles


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    new_docs = gen_new_docs()
    written = 0
    for doc in new_docs:
        path = OUTPUT_DIR / f"{doc['title']}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        written += 1

    patched, existing_articles = patch_existing_docs()

    # 统计
    stats: dict[str, dict] = {}
    for doc in new_docs:
        dt = doc["doc_type"]
        s = stats.setdefault(dt, {"files": 0, "articles": 0})
        s["files"] += 1
        s["articles"] += count_articles(doc)
    for p in sorted(OUTPUT_DIR.glob("*.json")):
        if p.name == "index.json" or p.name.startswith("_"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("doc_type") in ("law", "regulation"):
            dt = data["doc_type"]
            s = stats.setdefault(dt, {"files": 0, "articles": 0})
            s["files"] += 1
            s["articles"] += sum(len(ch.get("articles") or []) for ch in data.get("chapters") or [])

    print("=" * 56)
    print(f"新写语料文件: {written} 个；为既有法规补 doc_type: {patched} 个")
    print(f"{'doc_type':<12}{'类别':<10}{'文件数':>6}{'条数':>8}")
    total_files = total_articles = 0
    for dt in ("law", "regulation", "company", "sop", "plan", "case"):
        s = stats.get(dt, {"files": 0, "articles": 0})
        total_files += s["files"]
        total_articles += s["articles"]
        print(f"{dt:<12}{DOC_TYPE_LABEL[dt]:<10}{s['files']:>6}{s['articles']:>8}")
    print("-" * 56)
    print(f"{'合计':<12}{'':<10}{total_files:>6}{total_articles:>8}")
    print("=" * 56)
    ok = all(stats.get(dt, {}).get("articles", 0) > 0 for dt in ("law", "regulation", "company", "sop", "plan", "case"))
    ok = ok and total_articles > 1000
    print("O4 验收（六类均有数据且合计>1000条）:", "通过 ✅" if ok else "未通过 ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
