# -*- coding: utf-8 -*-
"""种子 URL 直抓器（O4 通用）：给定「真实全文页 URL + doc_type」列表 → 抓正文 → 保存。

用于 case（应急管理部/省应急厅官方事故调查报告）、plan（gov.cn 预案）等，
规避列表页 JS 渲染问题：直接用 web_search 收集到的正文 URL 作种子。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from crawler_gov_plan import parse_generic  # noqa: E402
from crawler_safehoo import fetch, save_doc, split_into_chapters  # noqa: E402

# 应急管理部官方事故调查报告/评估报告正文（web_search 收集）
CASE_SEEDS = [
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
    ("宁夏银川富洋烧烤店“6·21”特别重大燃气爆炸事故整改评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202502/t20250214_513847.shtml"),
    ("江西新余佳乐苑临街店铺“1·24”特别重大火灾事故整改评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202510/t20251017_561803.shtml"),
    ("北京丰台长峰医院“4·18”重大火灾事故整改评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202501/t20250117_513832.shtml"),
    ("内蒙古阿拉善新井煤业“2·22”坍塌事故整改评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202411/t20241122_512786.shtml"),
    ("河南安阳凯信达“11·21”火灾事故整改评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202411/t20241122_512785.shtml"),
    ("陕西商洛“7·19”桥梁垮塌整改评估报告",
     "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202605/t20260522_604598.shtml"),
]


def main() -> int:
    total = 0
    for title, url in CASE_SEEDS:
        html = fetch(url, retries=1)
        if not html:
            print(f"  ✗ 抓取失败 {title[:30]}")
            continue
        t2, paras = parse_generic(html)
        if len(paras) < 10:
            print(f"  ✗ 正文不足 {title[:30]}（{len(paras)} 段）")
            continue
        chapters = split_into_chapters(paras)
        if save_doc(title, "case", "典型事故案例", url, chapters, source="应急管理部"):
            total += 1
            arts = sum(len(c["articles"]) for c in chapters)
            print(f"  ✓ {title[:40]}（{len(chapters)} 章 {arts} 条）")
        time.sleep(0.8)
    print(f"官方事故报告抓取完成：{total} 篇")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
