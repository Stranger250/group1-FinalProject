# -*- coding: utf-8 -*-
"""应急管理部事故调查报告 PDF 爬虫（O4/case）：报告页 → PDF 附件 → pdfplumber 提取全文。

官方特别重大事故调查报告以 PDF 附件发布（页面仅标题+摘要），PDF 内为完整全文
（事故概况/直接原因/间接原因/责任追究/整改措施等，是最高质量的 case 语料）。
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

from crawler_safehoo import OUTPUT_DIR, fetch, save_doc  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"}

# (标题, 报告页 URL)
SEEDS = [
    ("江西新余佳乐苑临街店铺“1·24”特别重大火灾事故调查报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202409/t20240921_501979.shtml"),
    ("宁夏银川富洋烧烤店“6·21”特别重大燃气爆炸事故调查报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202401/t20240127_476487.shtml"),
    ("北京丰台长峰医院“4·18”重大火灾事故调查报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202310/t20231025_466731.shtml"),
    ("内蒙古阿拉善新井煤业露天煤矿“2·22”特别重大坍塌事故调查报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202308/t20230829_460802.shtml"),
    ("河南安阳市凯信达商贸有限公司“11·21”特别重大火灾事故调查报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202308/t20230829_460801.shtml"),
    ("湖南长沙“4·29”特别重大居民自建房倒塌事故调查报告",
     "https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/2023dcbg_5532/202305/t20230521_451391.shtml"),
    ("北京密云太师屯镇养老照料中心“7·28”暴雨洪水特别重大灾害调查评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202606/t20260618_608227.shtml"),
    ("陕西商洛“7·19”高速公路桥梁垮塌灾害调查评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202503/t20250327_531682.shtml"),
    # 第三轮补充（整改评估报告）
    ("湖南长沙“4·29”特别重大居民自建房倒塌事故整改和防范措施落实情况评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202406/t20240621_492432.shtml"),
    ("江西新余佳乐苑临街店铺“1·24”特别重大火灾事故整改和防范措施落实情况评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202510/t20251017_561803.shtml"),
    ("陕西商洛“7·19”高速公路桥梁垮塌灾害整改和防范措施落实情况评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202605/t20260522_604598.shtml"),
    ("宁夏银川富洋烧烤店“6·21”特别重大燃气爆炸事故整改和防范措施落实情况评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202502/t20250214_513847.shtml"),
]


def find_pdf_url(page_html: str, page_url: str) -> str | None:
    m = re.search(r'href="([^"]+\.pdf)"', page_html, re.I)
    if not m:
        return None
    href = m.group(1)
    if href.startswith("http"):
        return href
    # 相对路径
    base = page_url.rsplit("/", 1)[0]
    href = re.sub(r"^\./", "", href)
    return f"{base}/{href}"


def pdf_to_paras(pdf_bytes: bytes) -> list[str]:
    import pdfplumber

    paras: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                paras.append(line)
    # 按段落聚合：连续短行合并（PDF 文本按行切，需要重排）
    merged: list[str] = []
    buf = ""
    for line in paras:
        # 行以句号/引号结束或行尾无标点且下一行开头无编号 → 合并
        if buf and (line[0].isdigit() or line[0] in "一二三四五六七八九十（(" or buf.endswith(("。", "；", "”"))):
            merged.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        merged.append(buf)
    # 过滤过短/噪声行
    out = [m for m in merged if len(m) >= 12]
    return out


def main() -> int:
    total = 0
    for title, page_url in SEEDS:
        html = fetch(page_url, retries=1)
        if not html:
            print(f"  ✗ 页面失败 {title[:30]}")
            continue
        pdf_url = find_pdf_url(html, page_url)
        if not pdf_url:
            print(f"  ✗ 无 PDF 附件 {title[:30]}")
            continue
        try:
            r = requests.get(pdf_url, headers=UA, timeout=60)
            if r.status_code != 200 or len(r.content) < 1000:
                print(f"  ✗ PDF 下载失败 {title[:30]} ({r.status_code})")
                continue
            paras = pdf_to_paras(r.content)
        except Exception as e:
            print(f"  ✗ PDF 解析失败 {title[:30]}: {e}")
            continue
        if len(paras) < 20:
            print(f"  ✗ 正文不足 {title[:30]}（{len(paras)} 段）")
            continue
        # 分条：按段落为条，无章节结构（PDF 文本）
        chapters = [{
            "chapter": "正文",
            "articles": [{"no": f"第{i+1}条", "content": p} for i, p in enumerate(paras)],
        }]
        if save_doc(title, "case", "典型事故案例", page_url, chapters, source="应急管理部"):
            total += 1
            print(f"  ✓ {title[:40]}（{len(paras)} 条，{pdf_url.split('/')[-1]}）")
        time.sleep(0.8)
    print(f"官方 PDF 报告抓取完成：{total} 篇")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
