# -*- coding: utf-8 -*-
"""应急管理部事故报告批量爬虫（O4/case 扩充）：政府信息公开「事故及灾害查处」全部分页 → 筛报告类 → 抓取。

列表：https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/46/index_1771{_N}.shtml（共 56 页 ~837 条）
筛选：标题含「调查报告/调查评估报告/整改和防范措施落实情况评估报告」
正文：优先 PDF 附件（pdfplumber），无附件用页面正文（parse_generic）。
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

from crawler_gov_plan import parse_generic  # noqa: E402
from crawler_safehoo import OUTPUT_DIR, fetch, save_doc, split_into_chapters  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"}
LIST_BASE = "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/46/"
KEYWORDS = ("调查报告", "调查评估报告", "整改和防范措施落实情况评估报告")


def collect_report_links(max_pages: int = 56) -> list[tuple[str, str]]:
    """抓列表分页 → (绝对URL, 标题)。"""
    out: list[tuple[str, str]] = []
    for i in range(max_pages):
        url = LIST_BASE + ("index_1771.shtml" if i == 0 else f"index_1771_{i}.shtml")
        html = fetch(url)
        if not html:
            print(f"  第 {i} 页抓取失败")
            continue
        for href, title in re.findall(r'href="([^"]+\.shtml)"[^>]*>([^<]{8,100})</a>', html):
            title = title.strip()
            if not any(k in title for k in KEYWORDS):
                continue
            if "评估" in title and "报告" in title and "整改" not in title and "调查" not in title:
                continue
            full = href if href.startswith("http") else (
                "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/" + href.lstrip("./").lstrip("/")
                if href.startswith("../")
                else "https://www.mem.gov.cn" + href if href.startswith("/") else href
            )
            if (full, title) not in out:
                out.append((full, title))
        time.sleep(0.4)
    return out


def find_pdf_url(html: str, page_url: str) -> str | None:
    m = re.search(r'href="([^"]+\.pdf)"', html, re.I)
    if not m:
        return None
    href = m.group(1)
    if href.startswith("http"):
        return href
    base = page_url.rsplit("/", 1)[0]
    href = re.sub(r"^\.\.?/", "", href)
    return f"{base}/{href}"


def pdf_to_paras(pdf_bytes: bytes) -> list[str]:
    import pdfplumber

    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                if line.strip():
                    lines.append(line.strip())
    merged: list[str] = []
    buf = ""
    for line in lines:
        if buf and (line[0].isdigit() or line[0] in "一二三四五六七八九十（(" or buf.endswith(("。", "；", "”"))):
            merged.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        merged.append(buf)
    return [m for m in merged if len(m) >= 12]


def main() -> int:
    print("收集报告链接...")
    links = collect_report_links()
    print(f"筛出报告类条目 {len(links)} 条")
    total = 0
    skipped_dup = 0
    for url, title in links:
        html = fetch(url, retries=1)
        if not html:
            continue
        # 已有同名文件跳过（幂等）
        safe = re.sub(r'[\\/:*?"<>|]', "_", title)[:80]
        if (OUTPUT_DIR / f"{safe}.json").exists():
            skipped_dup += 1
            continue
        chapters = None
        pdf_url = find_pdf_url(html, url)
        if pdf_url:
            try:
                r = requests.get(pdf_url, headers=UA, timeout=60)
                if r.status_code == 200 and len(r.content) > 1000:
                    paras = pdf_to_paras(r.content)
                    if len(paras) >= 15:
                        chapters = [{"chapter": "正文", "articles": [{"no": f"第{i+1}条", "content": p}
                                                                     for i, p in enumerate(paras)]}]
            except Exception:
                pass
        if chapters is None:
            _t, paras = parse_generic(html)
            if len(paras) >= 15:
                chapters = split_into_chapters(paras)
        if chapters is None:
            print(f"  ✗ 提取失败 {title[:32]}")
            continue
        if save_doc(title, "case", "典型事故案例", url, chapters, source="应急管理部"):
            total += 1
            arts = sum(len(c["articles"]) for c in chapters)
            print(f"  ✓ {title[:36]}（{len(chapters)} 章 {arts} 条）")
        time.sleep(0.5)
    print(f"完成：新增 {total} 篇（跳过重复 {skipped_dup}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
