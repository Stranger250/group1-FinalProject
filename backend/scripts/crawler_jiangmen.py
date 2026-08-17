# -*- coding: utf-8 -*-
"""江门市应急管理局事故调查报告专栏批量爬虫（建设/交通类为主）。

列表：http://www.jiangmen.gov.cn/bmpd/jmsyjglj/zwgk/zdlyxxgk/scaqsgdcbgxx/（分页）
正文：报告页正文以 /attachment/ 的 PDF 附件发布 → pdfplumber 提取。
"""
import io
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

from crawler_gov_plan import parse_generic  # noqa: E402
from crawler_safehoo import fetch, save_doc, split_into_chapters  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"}
LIST = "http://www.jiangmen.gov.cn/bmpd/jmsyjglj/zwgk/zdlyxxgk/scaqsgdcbgxx/"


def pdf_to_paras(pdf_bytes: bytes) -> list[str]:
    import pdfplumber

    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                if line.strip():
                    lines.append(line.strip())
    merged, buf = [], ""
    for line in lines:
        if buf and (line[0].isdigit() or line[0] in "一二三四五六七八九十（(" or buf.endswith(("。", "；", "”"))):
            merged.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        merged.append(buf)
    return [m for m in merged if len(m) >= 12]


def collect(max_pages: int = 10) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i in range(max_pages):
        url = LIST if i == 0 else f"{LIST}index_{i}.html"
        html = fetch(url)
        if not html:
            url = LIST if i == 0 else f"{LIST}index_{i}.shtml"
            html = fetch(url)
        if not html:
            print(f"  第 {i} 页失败")
            continue
        links = re.findall(r'href="([^"]+)"[^>]*>([^<]{8,100})</a>', html)
        got = 0
        for href, title in links:
            title = title.strip()
            if ("调查" not in title and "评估" not in title) or "报告" not in title:
                continue
            full = href if href.startswith("http") else (
                "http://www.jiangmen.gov.cn" + href if href.startswith("/") else
                "http://www.jiangmen.gov.cn/bmpd/jmsyjglj/zwgk/zdlyxxgk/scaqsgdcbgxx/" + href.lstrip("./"))
            if (full, title) not in out:
                out.append((full, title))
                got += 1
        print(f"  第 {i} 页 +{got}")
        time.sleep(0.4)
    return out


def main() -> int:
    links = collect()
    print(f"共 {len(links)} 篇报告")
    total = 0
    for url, title in links:
        safe = re.sub(r'[\\/:*?"<>|]', "_", title)[:80]
        if (Path("../crawler_output") / f"{safe}.json").exists():
            continue
        html = fetch(url)
        if not html:
            continue
        # 正文优先取 /attachment/ 的 PDF 附件
        chapters = None
        pdf_m = re.search(r'href="(http[^"]*?/attachment/[^"]+\.pdf)"', html, re.I)
        if pdf_m:
            try:
                r = requests.get(pdf_m.group(1), headers=UA, timeout=60)
                if r.status_code == 200 and len(r.content) > 1000:
                    paras = pdf_to_paras(r.content)
                    if len(paras) >= 10:
                        chapters = [{"chapter": "正文", "articles": [{"no": f"第{i+1}条", "content": p}
                                                                     for i, p in enumerate(paras)]}]
            except Exception:
                pass
        if chapters is None:
            _t, paras = parse_generic(html)
            if len(paras) >= 10:
                chapters = split_into_chapters(paras)
        if chapters is None:
            print(f"  ✗ 提取失败 {title[:34]}")
            continue
        if save_doc(title, "case", "典型事故案例", url, chapters, source="政府网站公开"):
            total += 1
            arts = sum(len(c["articles"]) for c in chapters)
            print(f"  ✓ {title[:40]}（{len(chapters)} 章 {arts} 条）")
        time.sleep(0.4)
    print(f"完成：新增 {total} 篇")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
