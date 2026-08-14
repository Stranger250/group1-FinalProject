# -*- coding: utf-8 -*-
"""
数据盘点审计：扫描 crawler_output/*.json，输出 _rag_data_audit.json。

输出字段（与既有结构保持一致，可 drop-in 替换）：
  files[]       每部法规：title/category/chapters/articles/full_text_chars/doc_no/status/effective_date
  totals        files/chapters/articles/chars/cross_refs(第X条)/categories
  article_len   avg/min/max/count

用法（在 shudao 根目录）：
    python crawler/audit.py
"""
import glob
import json
import os
import re
import sys

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE, "crawler_output")
AUDIT_OUT = os.path.join(BASE, "docs", "_rag_data_audit.json")

# 正文中的"第X条"交叉引用（不含条号本身，只扫 content 字段，即真实引用）
_REF_RE = re.compile(r"第[一二三四五六七八九十百千零〇0-9０-９]+条")


def _count_refs(d):
    """返回 (内容内真实交叉引用数, 全文'第X条'字面出现数含条号头)。"""
    in_content = 0
    for c in d.get("chapters", []):
        for a in c.get("articles", []):
            in_content += len(_REF_RE.findall(a.get("content", "")))
    in_fulltext = len(_REF_RE.findall(d.get("full_text", "")))
    return in_content, in_fulltext


def audit():
    files = []
    totals = {"files": 0, "chapters": 0, "articles": 0, "chars": 0,
              "cross_refs(第X条)": 0, "ref_occurrences(第X条含条号)": 0,
              "categories": {}}
    lengths = []
    for path in sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.json"))):
        if path.endswith("index.json"):
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        chapters = d.get("chapters", [])
        n_art = sum(len(c.get("articles", [])) for c in chapters)
        chars = len(d.get("full_text", ""))
        refs, occ = _count_refs(d)
        for c in chapters:
            for a in c.get("articles", []):
                lengths.append(len(a.get("content", "")))
        files.append({
            "title": d.get("title", ""),
            "category": d.get("category", ""),
            "chapters": len(chapters),
            "articles": n_art,
            "full_text_chars": chars,
            "doc_no": d.get("doc_no", ""),
            "status": d.get("status", ""),
            "effective_date": d.get("effective_date", ""),
        })
        totals["files"] += 1
        totals["chapters"] += len(chapters)
        totals["articles"] += n_art
        totals["chars"] += chars
        totals["cross_refs(第X条)"] += refs
        totals["ref_occurrences(第X条含条号)"] += occ
        cat = d.get("category", "")
        totals["categories"][cat] = totals["categories"].get(cat, 0) + 1

    out = {
        "files": files,
        "totals": totals,
        "article_len": {
            "avg": round(sum(lengths) / len(lengths), 1) if lengths else 0,
            "min": min(lengths) if lengths else 0,
            "max": max(lengths) if lengths else 0,
            "count": len(lengths),
        },
    }
    with open(AUDIT_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"✅ 审计完成，已写入 {AUDIT_OUT}")
    print(f"   法规 {totals['files']} 部 / 章 {totals['chapters']} / 条 {totals['articles']} "
          f"/ 字符 {totals['chars']}")
    print(f"   交叉引用(内容内) {totals['cross_refs(第X条)']} 处；"
          f"'第X条'字面总出现 {totals['ref_occurrences(第X条含条号)']} 处(含条号头)")
    print(f"   条均 {out['article_len']['avg']} 字（{out['article_len']['min']}-"
          f"{out['article_len']['max']}）")
    print(f"   分类: {totals['categories']}")


if __name__ == "__main__":
    audit()
