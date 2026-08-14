# -*- coding: utf-8 -*-
"""
通道C：部门规章
首选：国务院政策文件库 API（聚合了各部委部门规章，比逐站爬更稳）
兜底：应急管理部 mem.gov.cn / 交通运输部 mot.gov.cn 直爬（选择器未实证）

政策文件库 API（无需认证）：
  GET https://sousuo.www.gov.cn/search-gov/data
    t=zhengcelibrary, q=关键词, childtype=bumenfile, bmfl=部门名,
    p/n(分页), type=gwyzcwjk
  记录含 title / source(发文机关) / pcode(文号) / pubtime / piclinksurl(正文链接)
"""
import re

from bs4 import BeautifulSoup

import config
from core.cleaner import clean_text
from core.http import HttpClient
from core.splitter import split_law_text


def _clean_html(raw):
    """去掉搜索结果标题里的 <em>/<br> 等标签并反转义。"""
    import html as _html
    import re as _re
    if not raw:
        return ""
    return _html.unescape(_re.sub(r'<[^>]+>', '', raw)).strip()


def _relevance(raw, keyword):
    """标题与关键词重合度：关键词全含 → 高权重；否则按标题长度差。"""
    title = _clean_html(raw)
    if keyword in title:
        return 1000 - len(title)      # 关键词被完全包含，标题越短越精准
    return -abs(len(title) - len(keyword))


def _format_pubtime(s):
    """把 '2016.10.10' / '2016-10-10' 归一化为 '2016-10-10'。"""
    if not s:
        return ""
    s = str(s).strip()
    return s.replace('.', '-').replace('/', '-') if s else ""


def _split_title(raw):
    """把标题拆成 (doc_no, title)。

    常见格式: '国家安全生产监督管理总局令（第88号）　　生产安全事故应急预案管理办法'
    或带站点后缀: '...办法__2016年第28号国务院公报_中国政府网'
    """
    s = _clean_html(raw)
    if not s:
        return "", ""
    # 去掉 '__..._中国政府网' 之类的站点后缀
    s = re.split(r'_{2,}', s)[0].strip()
    # 按全角/半角空格分词，若首段形如 'XX令（第X号）' 则拆为文号+法规名
    parts = [p for p in re.split(r'[　\s]+', s) if p]
    if len(parts) >= 2 and re.match(r'^[^（]*令（第[一二三四五六七八九十0-9]+号）$', parts[0]):
        return parts[0], parts[1]
    return "", s


class DeptSource:
    name = "dept"

    def __init__(self, http=None):
        self.http = http or HttpClient()

    # -------------------- 政策文件库 API --------------------
    def api_search(self, keyword, department=None, page=0, n=20):
        """国务院政策文件库检索，返回记录列表（展平所有分类）。"""
        params = {
            "t": "zhengcelibrary",
            "q": keyword,
            "searchfield": "title",          # 标题检索更精准
            "sort": "score",
            "sortType": 1,
            "p": page,
            "n": n,
            "type": "gwyzcwjk",
        }
        if department:
            params["childtype"] = "bumenfile"  # 部门文件
            params["bmfl"] = department
        resp = self.http.get(config.GOV_API, params=params)
        data = resp.json()
        # 列表在 searchVO.catMap.<分类>.listVO
        sv = data.get("searchVO") or {}
        catmap = sv.get("catMap") or {}
        recs = []
        for cat, v in catmap.items():
            if isinstance(v, dict) and v.get("listVO"):
                recs.extend(v["listVO"])
        return recs

    def fetch_from_api(self, keyword, department):
        """从政策文件库检索并抓取正文。"""
        recs = self.api_search(keyword, department)
        if not recs:
            raise RuntimeError(f"政策文件库未检索到「{keyword}」({department})")

        # 选标题关键词重合最多的记录（搜索结果可能混入相近文件）
        best = max(recs, key=lambda r: _relevance(r.get("title", ""), keyword))
        # 正文链接在 url 字段；piclinksurl 常为空
        url = best.get("url") or best.get("piclinksurl") or best.get("detailUrl")
        if not url:
            raise RuntimeError(f"记录无正文链接: {best.get('title')}")
        print(f"  命中: {_clean_html(best.get('title'))[:50]} -> {url}")

        data = self.fetch_article(url)
        # 标题/文号：优先搜索结果里的干净标题，其次页面标题
        raw_title = data["title"] or _clean_html(best.get("title")) or keyword
        doc_no, title = _split_title(raw_title)
        data["title"] = title or raw_title
        data["doc_no"] = best.get("pcode") or best.get("wenhao") or doc_no or data["doc_no"]
        data["publish_date"] = _format_pubtime(best.get("pubtimeStr")) or data["publish_date"]
        data["source"] = best.get("source") or data["source"]
        return data

    # -------------------- 通用正文页抓取 --------------------
    def fetch_article(self, url):
        """抓取 .htm/.shtml 静态正文页 → 标准 JSON dict。

        gov.cn 部分页面 HTML 标签不闭合，lxml 会把 DOM 解析坏（正文容器
        直接消失）。所以 lxml 提取不到正文时，用 html.parser 兜底重解析。
        """
        resp = self.http.get(url)
        # gov.cn 部分页面 HTML 标签不闭合，lxml 会把 DOM 解析坏导致正文容器
        # 消失；html.parser 更宽容。两个解析器各试一次，取文本更长的结果。
        soup_l = BeautifulSoup(resp.text, "lxml")
        soup_h = BeautifulSoup(resp.text, "html.parser")
        txt_l, txt_h = self._extract_body(soup_l), self._extract_body(soup_h)
        if len(txt_h) > len(txt_l):
            soup, full_text = soup_h, txt_h
        else:
            soup, full_text = soup_l, txt_l

        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            title = h1.get_text(strip=True)
        else:
            t = soup.find("title")
            title = t.get_text(strip=True) if t else ""

        return {
            "title": title,
            "doc_no": "",
            "category": "部门规章",
            "source": "gov.cn 政策文件库",
            "source_url": url,
            "publish_date": "",
            "effective_date": "",
            "status": "",
            "chapters": split_law_text(full_text),
            "full_text": full_text,
        }

    def _extract_body(self, soup):
        """按内容容器选择器取正文；失败则去导航后取整页文本。"""
        for sel in config.GOV_CONTENT_SELECTORS:
            node = soup.select_one(sel)
            if node:
                txt = clean_text(node.get_text("\n", strip=True))
                if len(txt) > 100:
                    return txt
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        return clean_text(soup.get_text("\n", strip=True))

    # -------------------- 主流程 --------------------
    def fetch(self, keyword, department="应急管理部", output_dir=None):
        """统一入口：政策文件库 API 为主。"""
        return self.fetch_from_api(keyword, department)
