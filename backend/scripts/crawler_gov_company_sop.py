# -*- coding: utf-8 -*-
"""企业制度/操作规程真实语料（O4/company+sop）：gov.cn 公开的制度汇编/规程全文直抓。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from crawler_gov_plan import parse_generic  # noqa: E402
from crawler_safehoo import fetch, save_doc, split_into_chapters  # noqa: E402

# (标题, URL, doc_type)
SEEDS = [
    # company：制度汇编/管理办法（政府网站公开全文）
    ("宣城宁国化工园区安全管理制度汇编",
     "https://www.ningguo.gov.cn/Xzgfxwjk/show/19277.html", "company"),
    ("市国资委监管企业安全生产监督管理办法",
     "https://www.gzw.sh.gov.cn/zcwj_gfxwj/20241218/e9b4ccc3bac24a5ea46fe2d6cd1f20f9.html", "company"),
    ("上海市人民政府关于进一步加强企业安全生产工作的通知实施意见",
     "https://www.shanghai.gov.cn/nw25060/20200820/0001-25060_23858.html", "company"),
    # sop/company：操作规程/隐患判定标准（条文式全文）
    ("交通运输行业重大事故隐患判定标准汇编",
     "https://jtt.hunan.gov.cn/jtt/jjzdgz/aqsc/hmd/202506/t20250616_33709669.html", "sop"),
    ("国家安全监管总局关于加强化工过程安全管理的指导意见",
     "https://www.mem.gov.cn/gk/gwgg/agwzlfl/yj_01/201308/t20130816_242220.shtml", "sop"),
    ("四川省烟花爆竹作业安全操作规程指导意见",
     "https://www.nanchong.gov.cn/yjglj/zwxx/zfxxgkzl/fdzdgknr/jdjc/aqsc/201506/t20150601_1643877.html", "sop"),
    # 第二轮补充
    ("克孜勒苏柯尔克孜自治州动火作业安全管理规定",
     "https://www.xjkz.gov.cn/xjkz/c101718/202512/5ed408492e7c4ee2a64a21e80e48231c.shtml", "sop"),
    ("煤层气地面开采安全规定（试行）",
     "https://www.mem.gov.cn/gk/gwgg/agwzlfl/zjl_01/201203/t20120306_233753.shtml", "sop"),
    ("交通运输行业重大事故隐患判定标准汇编",
     "https://jtt.hunan.gov.cn/jtt/jjzdgz/aqsc/hmd/202506/t20250616_33709669.html", "sop"),
]


def main() -> int:
    total = 0
    for title, url, doc_type in SEEDS:
        html = fetch(url, retries=1)
        if not html:
            print(f"  ✗ 抓取失败 {title[:30]}")
            continue
        t2, paras = parse_generic(html)
        if len(paras) < 15:
            print(f"  ✗ 正文不足 {title[:30]}（{len(paras)} 段）")
            continue
        chapters = split_into_chapters(paras)
        category = "企业规范" if doc_type == "company" else "安全操作规程"
        if save_doc(title, doc_type, category, url, chapters, source="政府网站公开"):
            total += 1
            arts = sum(len(c["articles"]) for c in chapters)
            print(f"  ✓ {title[:36]}（{len(chapters)} 章 {arts} 条）")
        time.sleep(1.0)
    print(f"制度/规程抓取完成：{total} 篇")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
