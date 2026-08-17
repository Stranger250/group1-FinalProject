# -*- coding: utf-8 -*-
"""真实语料爬虫（O4 重做：以爬取的真实公开内容替代生成语料）。

源：安全管理网 safehoo.com（公开免费的安全管理资料站）
  - /Case/*           典型事故案例（真实事故调查报告/案例分析）→ doc_type=case
  - /Manage/System/   企业安全管理制度 → doc_type=company
  - /Manage/duty/     岗位安全职责 → doc_type=company
  - /Manage/Edu/      安全教育培训管理 → doc_type=company
  - /Tech/*           安全技术/操作规程 → doc_type=sop

用法：cd backend && python scripts/crawler_safehoo.py [--section case|company|sop] [--limit N] [--sleep 1.0]
输出：crawler_output/{标题}.json（统一 schema，doc_type 六类），幂等（已存在跳过），限速防反爬。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"}
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "crawler_output"

# 栏目配置：名称 → (起始列表 URL, doc_type, category)
SECTIONS = {
    "case": {
        "urls": [
            "https://www.safehoo.com/Case/",
            "https://www.safehoo.com/Case/Case/Roadvehicle/",
            "https://www.safehoo.com/Case/Case/Vehicle/",
            "https://www.safehoo.com/Case/Case/krqtbz/",
            "https://www.safehoo.com/Case/Case/Flammableliquid/",
            "https://www.safehoo.com/Case/Case/civilpurposes/",
            "https://www.safehoo.com/Case/Case/Fireworks/",
            "https://www.safehoo.com/Case/Case/combustiblesolids/",
            "https://www.safehoo.com/Case/Case/Hightemperature/",
            "https://www.safehoo.com/Case/Case/Other/",
            "https://www.safehoo.com/Case/Case/Blaze/",
            "https://www.safehoo.com/Case/Case/Collapse/",
            "https://www.safehoo.com/Case/Case/Drop/",
            "https://www.safehoo.com/Case/Case/Electric/",
            "https://www.safehoo.com/Case/Case/Mechanical/",
        ],
        "doc_type": "case",
        "category": "典型事故案例",
    },
    "company": {
        "urls": [
            "https://www.safehoo.com/Manage/System/",
            "https://www.safehoo.com/Manage/duty/",
            "https://www.safehoo.com/Manage/Edu/",
            "https://www.safehoo.com/Manage/Group/",
            "https://www.safehoo.com/Manage/Check/",
        ],
        "doc_type": "company",
        "category": "企业规范",
    },
    "sop": {
        "urls": [
            "https://www.safehoo.com/Tech/Machine/",
            "https://www.safehoo.com/Tech/Chemical/",
            "https://www.safehoo.com/Tech/Electric/",
            "https://www.safehoo.com/Tech/Construction/",
            "https://www.safehoo.com/Tech/Coal/",
            "https://www.safehoo.com/Tech/Traffic/",
        ],
        "doc_type": "sop",
        "category": "安全操作规程",
    },
}

# 广告/导航噪音段落（过滤）
_NOISE = (
    "客服微信", "加入VIP", "版权声明", "本文由", "如需转载", "安全工程师",
    "试题", "考试", "培训报名", "广告", "扫一扫", "二维码", "更多资料", "点击下载",
)

_ARTICLE_RE = re.compile(r'href="(/[A-Za-z]+/[A-Za-z]+/[A-Za-z]+/\d+/\d+\.shtml)"[^>]*>([^<]{6,80})</a>')
_PAGE_RE = re.compile(r'href="([^"]*?/index(?:_\d+)?\.shtml)"[^>]*>([^<]{0,10})</a>')
_NOISE_RE = re.compile(r"|".join(map(re.escape, _NOISE)))
_SPLIT_RE = re.compile(r"(第[一二三四五六七八九十百0-9]+[章节部分条]|[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[）)])")


def fetch(url: str, retries: int = 1) -> str | None:
    for i in range(retries + 1):
        try:
            r = requests.get(url, headers=UA, timeout=25)
            raw = r.content
            for enc in ("utf-8", "gbk"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", errors="replace")
        except Exception:
            if i == retries:
                return None
            time.sleep(1.5 * (i + 1))
    return None


def collect_article_urls(list_url: str, max_pages: int = 6) -> list[str]:
    """列表页 → 文章链接（含分页翻页）。"""
    urls: list[str] = []
    seen_pages: set[str] = set()
    page = list_url
    for _ in range(max_pages):
        if page in seen_pages:
            break
        seen_pages.add(page)
        html = fetch(page)
        if not html:
            break
        for href, _t in _ARTICLE_RE.findall(html):
            full = "https://www.safehoo.com" + href if href.startswith("/") else href
            if full not in urls:
                urls.append(full)
        # 下一页
        nxt = None
        for href, txt in _PAGE_RE.findall(html):
            if "下一页" in txt or "下页" in txt or href.endswith("index.shtml") and page == list_url:
                nxt = href
                break
        if not nxt:
            # 常见分页：index_2.shtml
            m = re.search(r'href="([^"]*?/index_(\d+)\.shtml)"', html)
            if m:
                cur = int(m.group(2))
                if f"index_{cur+1}.shtml" in html:
                    nxt = m.group(1).replace(f"index_{cur}.shtml", f"index_{cur+1}.shtml")
        if not nxt:
            break
        page = nxt if nxt.startswith("http") else list_url.rsplit("/", 1)[0] + "/" + nxt.lstrip("/")
    return urls


def parse_article(html: str) -> tuple[str, list[str]]:
    """文章页 → (标题, 正文段落列表)（过滤导航/广告）。"""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S) or re.search(r"<title>(.*?)</title>", html, re.S)
    title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
    title = re.sub(r"[-_].*(安全|事故|管理|规程|预案|制度).*", "", title).strip() or title
    # 正文：优先正文容器，回退全部 <p>
    body = html
    for cls in ("art_content", "article-content", "artContent", "content", "view", "news_content", "con_text"):
        m2 = re.search(rf'<div[^>]*class="[^"]*{cls}[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>', html)
        if not m2:
            m2 = re.search(rf'<div[^>]*class="[^"]*{cls}[^"]*"[^>]*>([\s\S]*?)</div>', html)
        if m2:
            body = m2.group(1)
            break
    paras: list[str] = []
    for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S):
        text = re.sub(r"<[^>]+>", "", p)
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\u3000", " ").replace("&nbsp;", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if not text or len(text) < 12:
            continue
        if _NOISE_RE.search(text) and len(text) < 120:
            continue
        paras.append(text)
    return title, paras


def split_into_chapters(paras: list[str]) -> list[dict]:
    """段落 → 章节结构：标题行（章节关键词开头）为章节名，其余为条款。

    无章节标题的文章统一归入「正文」章节；条号自动编号。
    """
    chapters: list[dict] = []
    cur = {"chapter": "正文", "articles": []}
    seq = 0
    for text in paras:
        # 章节标题启发：短行 + 常见章节词
        is_heading = (
            len(text) <= 30
            and any(k in text for k in ("事故概况", "事故经过", "直接原因", "间接原因", "原因分析",
                                         "责任追究", "处理结果", "整改措施", "防范措施", "警示", "教训",
                                         "第一章", "第二章", "第三章", "第四章", "第五章", "第六章",
                                         "总则", "适用范围", "职责", "管理", "附则", "一、", "二、", "三、",
                                         "四、", "五、", "六、", "七、", "八、", "九、", "十、"))
        )
        if is_heading and cur["articles"]:
            chapters.append(cur)
            cur = {"chapter": text, "articles": []}
        elif is_heading and not cur["articles"]:
            cur["chapter"] = text
        else:
            seq += 1
            cur["articles"].append({"no": f"第{seq}条", "content": text})
    if cur["articles"]:
        chapters.append(cur)
    # 过滤空章节
    chapters = [c for c in chapters if c["articles"]]
    return chapters


def save_doc(title: str, doc_type: str, category: str, source_url: str, chapters: list[dict],
             source: str = "安全管理网") -> bool:
    if not title or not chapters:
        return False
    # 文件名校验：非法字符替换
    safe = re.sub(r'[\\/:*?"<>|]', "_", title)[:80]
    path = OUTPUT_DIR / f"{safe}.json"
    if path.exists():
        return False  # 幂等跳过
    doc = {
        "title": title,
        "doc_no": "",
        "category": category,
        "doc_type": doc_type,
        "doc_level": 2,
        "region": "国家",
        "source": source,
        "source_url": source_url,
        "publish_date": "",
        "effective_date": "",
        "status": "现行有效",
        "chapters": chapters,
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def crawl_section(section: str, limit: int, sleep: float) -> int:
    cfg = SECTIONS[section]
    total = 0
    skipped = 0
    for list_url in cfg["urls"]:
        if limit and total >= limit:
            break
        print(f"[{section}] 列表 {list_url}")
        art_urls = collect_article_urls(list_url, max_pages=4)
        print(f"  发现 {len(art_urls)} 篇文章")
        for url in art_urls:
            if limit and total >= limit:
                break
            html = fetch(url)
            if not html:
                continue
            title, paras = parse_article(html)
            # 短文章过滤：正文段落 <5 视为会员截断/摘要页，丢弃（safehoo 部分文章仅 VIP 可见全文）
            if len(paras) < 5:
                skipped += 1
                continue
            chapters = split_into_chapters(paras)
            if save_doc(title, cfg["doc_type"], cfg["category"], url, chapters):
                total += 1
                arts = sum(len(c["articles"]) for c in chapters)
                print(f"  ✓ {title[:36]}（{len(chapters)} 章 {arts} 条）")
            time.sleep(sleep)
    print(f"[{section}] 完成：{total} 篇（跳过短文章 {skipped} 篇）")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="safehoo 真实语料爬虫")
    ap.add_argument("--section", choices=list(SECTIONS), help="抓取栏目；缺省全部")
    ap.add_argument("--limit", type=int, default=0, help="本栏目最多抓取篇数（0=不限制）")
    ap.add_argument("--sleep", type=float, default=0.8, help="请求间隔秒（防反爬）")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sections = [args.section] if args.section else list(SECTIONS)
    total = 0
    for sec in sections:
        n = crawl_section(sec, args.limit, args.sleep)
        total += n
        print(f"[{sec}] 完成：{n} 篇")
    # 统计
    stats: dict[str, int] = {}
    for p in OUTPUT_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            dt = d.get("doc_type") or "法规"
            stats[dt] = stats.get(dt, 0) + 1
        except Exception:
            pass
    print("crawler_output 现有文件数按 doc_type：", stats)
    print(f"本次新增：{total} 篇")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
