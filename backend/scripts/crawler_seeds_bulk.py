# -*- coding: utf-8 -*-
"""通用种子批量爬虫：给定 (标题, URL, doc_type) 列表 → 自动识别 PDF/docx/HTML 提取 → 保存。

用于快速扩充语料：case（市级/官方事故报告）、plan（gov.cn 预案）、company/sop（gov.cn 制度规程）。
"""
from __future__ import annotations

import io
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

# (标题, URL, doc_type)
SEEDS: list[tuple[str, str, str]] = [
    # ===== case：政府/官方报告全文 =====
    ("上海石油化工股份有限公司“6·18”1#乙二醇装置爆炸事故调查报告",
     "https://zh.wikisource.org/zh-hans/%E4%B8%8A%E6%B5%B7%E7%9F%B3%E6%B2%B9%E5%8C%96%E5%B7%A5%E8%82%A1%E4%BB%BD%E6%9C%89%E9%99%90%E5%85%AC%E5%8F%B8%E2%80%9C6%C2%B718%E2%80%9D1%EF%BC%83%E4%B9%99%E4%BA%8C%E9%86%87%E8%A3%85%E7%BD%AE%E7%88%86%E7%82%B8%E4%BA%8B%E6%95%85%E8%B0%83%E6%9F%A5%E6%8A%A5%E5%91%8A",
     "case"),
    ("鄂州市葛店城市综合体项目“12·8”较大起重伤害事故调查报告",
     "https://www.wangkanglawyer.com/sgdcbg/", "case"),
    # ===== plan：gov.cn 预案 =====
    ("重庆市涪陵区生产安全事故应急预案",
     "https://www.fl.gov.cn/zwgk_206/zfxxgk/fdzdgknr/yjya/202406/t20240625_13352742.html", "plan"),
    ("兰州市突发环境事件应急预案",
     "https://www.lanzhou.gov.cn/art/2024/9/20/art_15176_1413681.html", "plan"),
    # ===== plan：建设/交通类预案（蜀道业务相关）=====
    ("公路交通突发事件应急预案",
     "https://xxgk.mot.gov.cn/jigou/bgt/202006/t20200623_3307202.html", "plan"),
    ("吉林省高速公路突发事件应急预案",
     "https://jtyst.jl.gov.cn/zw_133208/yjgl/yjya/202311/t20231115_8836714.html", "plan"),
    ("涪陵区高速公路突发事件应急预案",
     "http://www.fl.gov.cn/zfxxgk_206/fdzdgknr/yjgl/yjyan/202112/t20211223_10221168.html", "plan"),
    ("义乌市城市桥梁隧道突发事件应急预案",
     "https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web3549/site/attach/0/9e76b7444641481e8705505fcf2d8f54.pdf", "plan"),
    ("浦东新区处置桥梁隧道运行事故应急预案",
     "https://www.pudong.gov.cn/zwgk/14537.gkml_ywl_dlgy/2026/105/354490.html", "plan"),
    ("济宁市兖州区公路工程生产安全事故应急预案",
     "https://www.jining.gov.cn/api-gateway/jpaas-jpolicy-web-server/front/info/detail?iid=15090", "plan"),
    # ===== company：建设类制度 =====
    ("铁路营业线施工安全管理办法",
     "https://www.nra.gov.cn/xxgk/gkml/ztjg/gfzd/gfxw/bumen/zhs/202110/t20211012_327953.shtml", "company"),
    ("隧道施工安全九条规定",
     "https://xxgk.mot.gov.cn/jigou/aqyzljlglj/202006/t20200623_3316167.html", "sop"),
    ("南山西丽“6·7”一般机械伤害事故调查报告",
     "https://www.szns.gov.cn/nsqajj/gkmlpt/content/12/12530/post_12530410.html", "case"),
    ("光明区新院项目一般触电事故调查报告",
     "https://www.szgm.gov.cn/attachment/1/1713/1713669/12782001.pdf", "case"),
    ("晋安新店福州斯曼巴体育发展有限公司“12·24”一般机械伤害事故调查报告",
     "https://www.fzja.gov.cn/xjwz/zwgk/zfxxgkzdgz/aqsc/sgfxjyd/202605/P020260526330196537018.pdf", "case"),
    ("中国能源建设集团山西电力建设有限公司项目安全生产管理制度",
     "https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web1941/site/attach/0/2ccb2577819c4c1cbf64cd561c826969.pdf",
     "company"),
]


def extract_from_bytes(data: bytes, url: str) -> list[str]:
    """按 URL 后缀/内容识别 PDF / docx / HTML。"""
    low = url.lower()
    if low.endswith(".pdf"):
        import pdfplumber
        lines = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
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
    if low.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(data))
        paras = [p.text.strip() for p in doc.paragraphs if len(p.text.strip()) >= 12]
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells and len(" | ".join(cells)) >= 12:
                    paras.append(" | ".join(cells))
        return paras
    # HTML
    try:
        html = data.decode("utf-8", errors="replace")
    except Exception:
        return []
    _t, paras = parse_generic(html)
    return paras


def main() -> int:
    total = 0
    for title, url, doc_type in SEEDS:
        safe = re.sub(r'[\\/:*?"<>|]', "_", title)[:80]
        if (OUTPUT_DIR / f"{safe}.json").exists():
            print(f"  - 跳过(已存在) {title[:30]}")
            continue
        try:
            # verify=False：部分政府站点 SSL 证书链不完整（BAD_ECPOINT），内容本身可信
            r = requests.get(url, headers=UA, timeout=60, verify=False)
            if r.status_code != 200:
                print(f"  ✗ HTTP {r.status_code} {title[:30]}")
                continue
            data = r.content
            paras = extract_from_bytes(data, url)
        except Exception as e:
            print(f"  ✗ 失败 {title[:30]}: {e}")
            continue
        if len(paras) < 10:
            print(f"  ✗ 内容不足 {title[:30]}（{len(paras)} 段）")
            continue
        chapters = [{"chapter": "正文", "articles": [{"no": f"第{i+1}条", "content": p}
                                                     for i, p in enumerate(paras)]}]
        cat = {"case": "典型事故案例", "plan": "应急预案", "company": "企业规范", "sop": "安全操作规程"}[doc_type]
        if save_doc(title, doc_type, cat, url, chapters, source="政府网站公开"):
            total += 1
            print(f"  ✓ {title[:40]}（{len(paras)} 条）")
        time.sleep(0.5)
    print(f"完成：新增 {total} 篇")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
