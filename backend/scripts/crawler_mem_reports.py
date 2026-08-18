# -*- coding: utf-8 -*-
"""应急管理部事故调查报告爬虫（O4/case）：按年份目录抓取官方特别重大事故调查报告全文。

列表：https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/{year}dcbg/（HTML 表格）
正文：zfxxgkpt 站群结构，复用 parse_generic 提取。
输出：crawler_output/{标题}.json（doc_type=case，source=应急管理部）。
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from crawler_gov_plan import parse_generic  # noqa: E402
from crawler_safehoo import fetch, save_doc, split_into_chapters  # noqa: E402

YEARS = ["2026", "2025", "2024", "2023", "2022", "2021"]

# 报告正文链接模式（zfxxgkpt 页）
_REPORT_RE = re.compile(r'href="(https://www\.mem\.gov\.cn/gk/zfxxgkpt/[^"]+\.shtml)"[^>]*>([^<]{8,80})</a>')


def collect_reports(year_url: str) -> list[tuple[str, str]]:
    html = fetch(year_url)
    if not html:
        return []
    out = []
    for href, title in _REPORT_RE.findall(html):
        title = title.strip()
        # 只看调查报告/评估报告（排除其他栏目混入）
        if "报告" not in title and "调查" not in title:
            continue
        if (href, title) not in out:
            out.append((href, title))
    return out


def main() -> int:
    total = 0
    for year in YEARS:
        year_url = f"https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/{year}dcbg/"
        reports = collect_reports(year_url)
        print(f"[{year}] 发现 {len(reports)} 篇报告")
        for url, title in reports:
            html = fetch(url)
            if not html:
                continue
            t2, paras = parse_generic(html)
            if len(paras) < 10:
                print(f"  ✗ 正文不足 {title[:30]}（{len(paras)} 段）")
                continue
            chapters = split_into_chapters(paras)
            if save_doc(title or t2, "case", "典型事故案例", url, chapters, source="应急管理部"):
                total += 1
                arts = sum(len(c["articles"]) for c in chapters)
                print(f"  ✓ {title[:40]}（{len(chapters)} 章 {arts} 条）")
            time.sleep(0.8)
    print(f"mem.gov.cn 报告抓取完成：{total} 篇")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
