# -*- coding: utf-8 -*-
"""应急预案真实语料爬虫（O4/plan）：抓取政府网站公开发布的应急预案全文。

种子 URL 来自 web_search 收集的 gov.cn 预案公开页（真实全文，正文完整无会员截断）。
输出：crawler_output/{标题}.json（doc_type=plan），复用 crawler_safehoo 的解析/分条逻辑。

用法：cd backend && python scripts/crawler_gov_plan.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from crawler_safehoo import fetch, parse_article, split_into_chapters, save_doc  # noqa: E402

# 种子：政府网站公开的应急预案全文页（真实来源）
SEED_URLS = [
    "https://changzhi.gov.cn/xxgkml/ggqsydw/srlyxgs/yjgl_2786/yjya_2789/201804/t20180420_1195165.shtml",  # 长治热力综合应急预案
    "https://www.sz.gov.cn/zfgb/2017/gb1003/content/post_4987803.html",  # 深圳市生产安全事故应急预案
    "http://www.cnts.gov.cn/gkmlpt/content/2/2236/post_2236048.html?jump=false",  # 台山市
    "https://public.xinzheng.gov.cn/D0104X/2028026.jhtml",  # 新郑市
    "https://www.mee.gov.cn/zcwj/zyygwj/202502/t20250225_1102851.shtml",  # 国家突发事件总体应急预案
    "https://yjj.anyang.gov.cn/2022/11-10/2365897.html",  # 安阳市
    "http://yjgl.gansu.gov.cn/yjgl/c112872/202603/174293385.shtml",  # 甘肃省（征求意见稿）
    "https://www.gz.gov.cn/gfxwj/sbmgfxwj/gzsyjglj/content/post_5486584.html",  # 广州市实施细则
    "https://hunan.gov.cn/hnszf/xxgk/wjk/szbm_1/szfzcbm_19689/syjgt/gfxwj_19835_22/201901/t20190114_5259863.html",  # 湖南省实施细则
    # 第二轮补充（web_search 收集）
    "http://www.suzhou.gov.cn/szsrmzf/gbqtwj/202505/d2002d9b0f954ad197e52678d328fa04.shtml",  # 苏州市较大以上生产安全事故应急预案
    "https://zwgk.shcn.gov.cn/xxgk/yjgl-zw/2024/333/75679.html",  # 长宁区生产安全事故专项应急预案
    "https://www.pudong.gov.cn/zwgk/14520.gkml_ywl_yjgl/2023/300/318972.html",  # 川沙新镇生产安全事故专项应急预案
    "https://gxq.cq.gov.cn/zwgk_202/fdzdgknr/yjya/yjya/202412/t20241220_13911770_wap.html",  # 重庆高新区
    "https://www.jining.gov.cn/api-gateway/jpaas-jpolicy-web-server/front/info/explain?iid=u03XNgfgiMvPZbwiCMEyl",  # 济宁兖州公路工程
]

_NOISE = (
    "客服", "扫码", "二维码", "版权所有", "ICP备案", "网站标识码", "主办单位",
    "联系我们", "网站地图", "打印", "关闭", "分享", "相关链接", "返回",
)


def _match_div(html: str, start: int) -> int:
    """从 <div ...> 的 start 位置开始做嵌套平衡匹配，返回对应 </div> 结束位置。"""
    depth = 0
    i = start
    while i < len(html):
        open_m = re.compile(r"<div\b").search(html, i)
        close_m = re.compile(r"</div>").search(html, i)
        if open_m is None and close_m is None:
            break
        if open_m is not None and (close_m is None or open_m.start() < close_m.start()):
            depth += 1
            i = open_m.end()
        else:
            depth -= 1
            i = close_m.end()
            if depth == 0:
                return i
    return len(html)


def parse_generic(html: str) -> tuple[str, list[str]]:
    """通用正文提取：标题 + 段落（适配 gov.cn 站群：<p> 或 <div><span> 两种正文格式）。"""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S) or re.search(r"<title>(.*?)</title>", html, re.S)
    title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
    title = re.sub(r"\s+", " ", title).strip(" -_|")
    # 正文容器（平衡匹配截取）
    body = html
    for cls in ("wj_neirong", "content_box", "content_body", "TRS_UEDITOR", "view", "TRS_Editor",
                "article-content", "article", "news_content", "pages_content", "xl_content",
                "cont", "content-main", "main-content", "content"):
        m2 = re.search(rf'<div[^>]*class="[^"]*{cls}[^"]*"[^>]*>', html)
        if m2:
            end = _match_div(html, m2.start())
            seg = html[m2.end():end]
            if len(re.sub(r"<[^>]+>", "", seg)) > 500:
                body = seg
                break
    # 段落提取：<p> + <div><span> 两种格式
    paras: list[str] = []
    for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S):
        text = re.sub(r"<[^>]+>", "", p)
        text = text.replace("\u3000", " ").replace("&nbsp;", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= 12:
            paras.append(text)
    for p in re.findall(r"<div[^>]*>\s*<span[^>]*>(.*?)</span>\s*</div>", body, re.S):
        text = re.sub(r"<[^>]+>", "", p)
        text = text.replace("\u3000", " ").replace("&nbsp;", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= 12:
            paras.append(text)
    # 去重（<p> 与 span 可能重叠）
    seen: set[str] = set()
    out: list[str] = []
    for t in paras:
        if t not in seen:
            seen.add(t)
            out.append(t)
    # 过滤导航/页脚
    out = [t for t in out if not (any(k in t for k in _NOISE) and len(t) < 60)]
    return title, out


def main() -> int:
    total = 0
    for url in SEED_URLS:
        html = fetch(url, retries=1)
        if not html:
            print(f"  ✗ 抓取失败 {url[:80]}")
            continue
        title, paras = parse_generic(html)
        if len(paras) < 10:
            print(f"  ✗ 正文不足 {title[:30]}（{len(paras)} 段）{url[:70]}")
            continue
        chapters = split_into_chapters(paras)
        if save_doc(title, "plan", "应急预案", url, chapters, source="政府网站公开"):
            total += 1
            arts = sum(len(c["articles"]) for c in chapters)
            print(f"  ✓ {title[:40]}（{len(chapters)} 章 {arts} 条）")
        time.sleep(1.0)
    print(f"plan 抓取完成：{total} 篇")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
