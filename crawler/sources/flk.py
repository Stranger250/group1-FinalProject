# -*- coding: utf-8 -*-
"""
通道A：国家法律法规数据库 flk.npc.gov.cn（全国人大）

全站为前端 SPA，不能抓 HTML，必须走官方 JSON API。
流程：搜索 -> 详情(元数据) -> 下载 docx -> 解析正文 -> 拆条款。

⚠️ 该接口可能随前端改版失效；字段名以 --probe 实际返回为准。
"""
import html
import io
import os
import re
import tempfile

import config
from core.cleaner import clean_text
from core.http import HttpClient
from core.splitter import split_law_text


class FlkSource:
    name = "flk"

    def __init__(self, http=None):
        self.http = http or HttpClient()

    # -------------------- 接口调用 --------------------
    def search(self, keyword, page=1, page_size=20):
        """标题模糊搜索，返回 (rows, total)。"""
        url = f"{config.FLK_BASE}/law-search/search/list"
        body = {
            "searchRange": 1,              # 1=标题检索, 2=正文检索（必须数字，数组会 500）
            "searchType": 2,               # 2=模糊
            "searchContent": keyword,
            "xgzlSearch": False,
            "orderByParam": {"order": "-1", "sort": ""},  # 必须 "-1"，升序会 500
            "pageNum": page,
            "pageSize": page_size,
        }
        resp = self.http.post(url, json=body,
                              headers={"Referer": f"{config.FLK_BASE}/detail"})
        data = resp.json()
        rows = data.get("rows") or []
        total = data.get("total") or 0
        return rows, total

    def detail(self, bbbs):
        """获取一部法规的元数据 + ossFile 路径。"""
        url = f"{config.FLK_BASE}/law-search/search/flfgDetails"
        resp = self.http.get(url, params={"bbbs": bbbs},
                             headers={"Referer": f"{config.FLK_BASE}/detail?id={bbbs}"})
        return resp.json()

    def download_url(self, bbbs, fmt="docx"):
        """获取带签名的 OSS 下载 URL（须即时消费）。"""
        url = f"{config.FLK_BASE}/law-search/download/pc"
        resp = self.http.get(url, params={"format": fmt, "bbbs": bbbs},
                             headers={"Referer": f"{config.FLK_BASE}/detail?id={bbbs}"})
        data = resp.json()
        dl = (data.get("data") or {})
        return dl.get("url") or None

    # -------------------- 正文解析 --------------------
    def _parse_docx_bytes(self, content):
        """把 docx 二进制解析为纯文本。"""
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError("缺少 python-docx，请先执行: pip install python-docx")
        doc = Document(io.BytesIO(content))
        parts = []
        for para in doc.paragraphs:
            t = para.text.strip()
            if t:
                parts.append(t)
        # 表格内容（部分法规条文在表格里）
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts)

    def _parse_pdf_bytes(self, content):
        """把 PDF 二进制解析为纯文本（兜底）。"""
        try:
            import pdfplumber
        except ImportError:
            raise RuntimeError("缺少 pdfplumber")
        parts = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t.strip():
                    parts.append(t)
        return "\n".join(parts)

    # -------------------- 元数据提取 --------------------
    # sxx 数字 → 文本（时效性）
    _SXX_TEXT = {"1": "已废止", "2": "已修改", "3": "现行有效", "4": "尚未生效"}

    def _extract_meta(self, detail):
        """从详情响应中提取元数据。字段名以实际返回为准，尽量宽松匹配。"""
        d = detail or {}
        # 详情可能返回 {code, data:{...}} 或 {code, data:{flfg:{...}}}
        data = d.get("data") or d
        flfg = data.get("flfg") if isinstance(data, dict) else None
        src = flfg if isinstance(flfg, dict) else data

        def get(*keys):
            for k in keys:
                if isinstance(src, dict) and src.get(k):
                    return src[k]
            return ""

        status = get("sxxName", "sxx", "status")
        if str(status).isdigit():
            status = self._SXX_TEXT.get(str(status), status)

        return {
            "title": get("title", "flfgTitle", "name"),
            "doc_no": get("whao", "docNo", "wh", "documentNo"),
            "category": get("flxz", "category", "lawTypeName"),
            "publish_date": get("gbrq", "publishDate", "gongbuDate"),
            "effective_date": get("sxrq", "effectiveDate", "shiXingDate"),
            "status": status,
        }

    # -------------------- 主流程 --------------------
    def fetch(self, keyword, output_dir=None):
        """
        按关键词抓取最匹配的规章，返回标准 JSON dict。
        keyword 应尽量精确到法规全称。
        """
        rows, total = self.search(keyword)
        if not rows:
            raise RuntimeError(f"flk 未检索到「{keyword}」")

        # 取标题最接近的一个（注意搜索结果 title 带 <em class='highlight'> 高亮标签）
        best = min(rows, key=lambda r: self._title_distance(r.get("title", ""), keyword))
        bbbs = best.get("bbbs")
        title = self._clean_title(best.get("title")) or keyword
        print(f"  命中: {title} (bbbs={bbbs})")

        detail = self.detail(bbbs)
        meta = self._extract_meta(detail)
        if not meta["title"]:
            meta["title"] = title

        # 尝试 docx -> pdf 兜底
        text = ""
        parse_error = ""
        for fmt in ("docx", "pdf"):
            url = self.download_url(bbbs, fmt=fmt)
            if not url:
                continue
            try:
                # 签名 URL 走 download()，跳过 robots 检查
                tmp_path = os.path.join(tempfile.gettempdir(),
                                        f"flk_{bbbs}.{fmt}")
                self.http.download(url, tmp_path)
                with open(tmp_path, "rb") as f:
                    content = f.read()
                if fmt == "docx":
                    text = self._parse_docx_bytes(content)
                else:
                    text = self._parse_pdf_bytes(content)
                if text.strip():
                    print(f"  ✅ 正文解析成功（{fmt}，{len(text)} 字符）")
                    break
            except Exception as e:
                parse_error = f"{fmt}: {e}"
                print(f"  ⚠️ {fmt} 解析失败：{e}")
                continue

        # 兜底：本地保存下载文件（供手动处理），仅在解析全失败时保留路径
        if not text.strip() and meta["title"]:
            parse_error = parse_error or "未获取到可解析的正文"

        full_text = clean_text(text)

        # 从正文题注里补文号（主席令/国务院令第X号），详情接口里往往没有
        doc_no = meta["doc_no"]
        if not doc_no:
            m = re.search(r'(?:主席令|国务院令|交通运输部令|应急管理部令|国家安全生产监督管理总局令)[\s　]*第[一二三四五六七八九十百千万零〇0-9０-９]+号',
                          full_text[:2000])
            if m:
                doc_no = re.sub(r'\s+', '', m.group(0))

        return {
            "title": meta["title"],
            "doc_no": doc_no,
            "category": meta["category"],
            "source": "flk.npc.gov.cn",
            "source_url": f"{config.FLK_BASE}/detail?id={bbbs}",
            "publish_date": meta["publish_date"],
            "effective_date": meta["effective_date"],
            "status": meta["status"],
            "chapters": split_law_text(full_text),
            "full_text": full_text,
            "parse_error": parse_error or None,
        }

    @staticmethod
    def _clean_title(raw):
        """去掉搜索结果里的高亮标签并反转义。"""
        if not raw:
            return ""
        text = re.sub(r'<[^>]+>', '', raw)
        return html.unescape(text).strip()

    @staticmethod
    def _title_distance(raw, keyword):
        """关键词完全包含则最优先，否则按长度差。"""
        title = FlkSource._clean_title(raw)
        if keyword in title:
            return 0
        return abs(len(title) - len(keyword))


if __name__ == "__main__":
    # 自测：python -m sources.flk  （从 crawler 目录运行）
    import sys
    if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    src = FlkSource()
    result = src.fetch("中华人民共和国安全生产法")
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
