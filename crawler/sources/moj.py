# -*- coding: utf-8 -*-
"""
通道B：国家行政法规库 xzfg.moj.gov.cn（司法部）

服务端渲染 HTML。
- 搜索：GET https://xzfg.moj.gov.cn/SearchAdvancedFront?title={关键词}
  （表单字段名是 title，非 keyword）
- 详情：GET /front/law/detail?LawID={id}

正文容器 class 经实测为 .law-chapter（2026-08 验证）。
"""
import re

from bs4 import BeautifulSoup

import config
from core.cleaner import clean_text
from core.http import HttpClient
from core.splitter import split_law_text

# 详情页正文容器（2026-08 实测 .law-chapter）
MOJ_CONTENT_SELECTORS = config.MOJ_CONTENT_SELECTORS + [
    ".law-chapter", ".law-content"
]


class MojSource:
    name = "moj"

    def __init__(self, http=None):
        self.http = http or HttpClient()

    # -------------------- 搜索 --------------------
    def search(self, keyword, max_results=10):
        """按标题搜索法规，返回 [{"law_id", "title"}, ...]。"""
        url = f"{config.MOJ_BASE}/SearchAdvancedFront"
        resp = self.http.get(url, params={"title": keyword})
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "LawID=" in href and "download" not in href:
                t = a.get_text(strip=True)
                if len(t) > 6:
                    lid = href.split("LawID=")[1].split("&")[0]
                    key = (t, lid)
                    if key not in seen:
                        seen.add(key)
                        results.append({"law_id": lid, "title": t})
        return results[:max_results]

    # -------------------- 按 LawID 抓取 --------------------
    def fetch_by_id(self, law_id, fallback_title=None):
        """按法规编号抓取，返回标准 JSON dict。"""
        url = f"{config.MOJ_BASE}/front/law/detail?LawID={law_id}"
        resp = self.http.get(url)
        soup = BeautifulSoup(resp.text, "lxml")

        full_text = self._extract_body(soup)
        # 法规名不在 h1/h2 里（章节都是 h2），优先用调用方传入的搜索结果标题
        title = fallback_title or self._extract_title(soup) \
            or f"行政法规(LawID={law_id})"
        print(f"  ✅ 正文提取完成（{len(full_text)} 字符）")

        return {
            "title": title,
            "doc_no": self._extract_meta(soup, "doc_no"),
            "category": "行政法规",
            "source": "xzfg.moj.gov.cn",
            "source_url": url,
            "publish_date": self._extract_meta(soup, "publish_date"),
            "effective_date": self._extract_meta(soup, "effective_date"),
            "status": self._extract_meta(soup, "status"),
            "chapters": split_law_text(full_text),
            "full_text": full_text,
        }

    # -------------------- 网页内容提取 --------------------
    def _extract_title(self, soup):
        """标题兜底：从正文里第一个非章节标题的行提取法规名。"""
        body = self._extract_body(soup)
        for line in body.split("\n"):
            line = line.strip()
            if line and not re.match(r'^第[一二三四五六七八九十百千万零〇0-9]+章', line) \
                    and "历史沿革" not in line:
                return line
        return ""

    def _extract_body(self, soup):
        """按选择器尝试取正文容器；都失败则回退 <body> 文本。"""
        for sel in MOJ_CONTENT_SELECTORS:
            node = soup.select_one(sel)
            if node:
                txt = node.get_text("\n", strip=True)
                # 过滤"下载Word/历史沿革/扫码下载"等按钮噪音
                txt = clean_text(txt)
                if len(txt) > 200:
                    return txt
        # 回退：body 去 script/style/nav 后取文本
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        return clean_text(soup.get_text("\n", strip=True))

    def _extract_meta(self, soup, kind):
        """从页面元信息里抠文号/日期/时效。"""
        body_text = soup.get_text("\n", strip=True)
        if kind == "doc_no":
            m = re.search(r'(国务院令\s*第\s*[一二三四五六七八九十0-9]+\s*号)', body_text)
            return re.sub(r'\s+', '', m.group(1)) if m else ""
        if kind == "publish_date":
            m = re.search(r'(?:公布|发布日期)[：:]?\s*([0-9]{4}[-/年][0-9]{1,2}[-/月][0-9]{1,2}日?)', body_text)
            return m.group(1) if m else ""
        if kind == "effective_date":
            m = re.search(r'(?:施行日期|施行时间)[：:]?\s*([0-9]{4}[-/年][0-9]{1,2}[-/月][0-9]{1,2}日?)', body_text)
            return m.group(1) if m else ""
        if kind == "status":
            m = re.search(r'(现行有效|有效|已废止|已修改)', body_text)
            return m.group(1) if m else ""
        return ""

    # -------------------- 主流程 --------------------
    def fetch(self, keyword, law_id=None, output_dir=None):
        """统一入口：优先 law_id；否则自动搜索取第一个结果。"""
        if law_id:
            return self.fetch_by_id(law_id, fallback_title=keyword)
        results = self.search(keyword)
        if not results:
            raise RuntimeError(f"moj 未检索到「{keyword}」")
        print(f"  🔍 搜索命中: {results[0]['title']} (LawID={results[0]['law_id']})")
        return self.fetch_by_id(results[0]["law_id"],
                                fallback_title=results[0]["title"])
