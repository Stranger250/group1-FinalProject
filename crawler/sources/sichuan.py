# -*- coding: utf-8 -*-
"""
通道D：四川省法规规章规范性文件数据库（rhpt.scspc.gov.cn，省人大常委会主办）

⚠️ 该站前端 Next.js + CloudWAF，纯 requests 会被 WAF 拦截（返回 304 空 body）。
   必须用 playwright 起真实 Chromium 才能访问。首次需：
     pip install playwright
     python -m playwright install chromium   （如慢用镜像：PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright）

接口（已用 playwright 实证 2026-08）：
- 列表：GET /flfgkgzd/publicPlatform/typeSearch
    type=2 政府规章 / type=1 地方性法规
    content=关键词, pageNum/pageSize, enableType(2=现行有效)
    响应 data.total + data.rows[]：fileDataId/fileTitle/formulationUnit/enableType/publishDate
- 详情：GET /flfgkgzd/publicPlatform/info?fileDataId=xxx
    响应 data.fileTitle/reportCnNumber(文号)/formulationUnit/enableType/publishDate
    /administrationDate/format(docx)/url(WPS预览链接)
- 正文：打开详情里的 url（wps.scspc.gov.cn 在线预览），等 JS 渲染后
    从 .pages-list 容器提取全文文本
"""
import re
import sys
import time

import config
from core.cleaner import clean_text
from core.splitter import split_law_text


class SichuanSource:
    name = "sichuan"

    def __init__(self, headless=True, wait_render=12):
        self.headless = headless
        self.wait_render = wait_render
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    # -------------------- playwright 生命周期 --------------------
    def _start(self):
        """启动 playwright + chromium（首次调用）。"""
        if self._browser:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "缺少 playwright：pip install playwright 后执行 "
                "python -m playwright install chromium")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"),
        )
        self._page = self._context.new_page()

    def _close(self):
        """关闭浏览器释放资源。"""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._context = None
            self._page = None
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    # -------------------- rhpt 接口（页面内 fetch） --------------------
    def _api(self, url):
        """在真实页面里用 fetch 调 rhpt 接口。

        ⚠️ 不能用 context.request.get()：那会触发 CloudWAF，把后续 WPS 预览
        降级成纯文本渲染（无 .is-horizontal-scroll 容器，正文逐字符换行）。
        页面内 fetch 走浏览器真实 JS 指纹，不触发降级。
        """
        self._start()
        if not self._page.url.startswith("https://rhpt.scspc.gov.cn"):
            try:
                self._page.goto("https://rhpt.scspc.gov.cn/flfgkgzd/gov",
                                wait_until="domcontentloaded", timeout=60000)
                time.sleep(1)
            except Exception:
                pass
        try:
            return self._page.evaluate(
                """async (u) => {
                    const r = await fetch(u, {
                        headers: {"Content-Type": "application/json"}
                    });
                    if (!r.ok) return {};
                    return await r.json();
                }""", url) or {}
        except Exception:
            return {}

    # -------------------- 列表检索 --------------------
    def search(self, keyword, file_type=2, max_pages=3, page_size=20,
               province_only=True):
        """按关键词检索四川规章，返回 [{"fileDataId","title","formulationUnit",
        "enableType","publishDate","administrationDate"}, ...]。

        file_type: 2=政府规章, 1=地方性法规
        province_only: 只保留四川省人民政府(省级)制定，过滤各地市规章
        """
        self._start()
        base = "https://rhpt.scspc.gov.cn/flfgkgzd/publicPlatform/typeSearch"
        results = []
        seen = set()
        for page_num in range(1, max_pages + 1):
            params = {
                "contentType": "",
                "content": keyword,
                "type": str(file_type),
                "formulationUnitList": "",
                "reportFileType": "",
                "enableType": "",          # 空=全部时效；"2"=现行有效
                "sortField": "1",
                "sort": "2",
                "pageSize": str(page_size),
                "pageNum": str(page_num),
                "publishDateStart": "",
                "publishDateEnd": "",
                "administrationDateStart": "",
                "administrationDateEnd": "",
            }
            # 拼 query 字符串（保留空参数）
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            data = self._api(f"{base}?{qs}").get("data") or {}
            rows = data.get("rows") or []
            if not rows:
                break
            for row in rows:
                if province_only:
                    unit = row.get("formulationUnit", "")
                    if "人民政府" in unit and "四川省" not in unit.split("人民政府")[0]:
                        # 只保留"四川省人民政府"（省级），去掉"成都市人民政府"等地市
                        if not unit.startswith("四川省人民政府"):
                            continue
                fid = row.get("fileDataId")
                if fid in seen:
                    continue
                seen.add(fid)
                results.append({
                    "fileDataId": fid,
                    "title": row.get("fileTitle", ""),
                    "formulationUnit": row.get("formulationUnit", ""),
                    "enableType": row.get("enableType", ""),
                    "publishDate": row.get("publishDate", ""),
                    "administrationDate": row.get("administrationDate", ""),
                })
            if len(rows) < page_size:
                break
        return results

    # -------------------- 详情元数据 --------------------
    def detail(self, file_data_id):
        """按 fileDataId 抓元数据 + 正文 WPS url。"""
        self._start()
        url = ("https://rhpt.scspc.gov.cn/flfgkgzd/publicPlatform/info"
               f"?fileDataId={file_data_id}")
        data = self._api(url).get("data") or {}
        d = data.get("data") or {}
        return {
            "title": d.get("fileTitle", ""),
            "doc_no": d.get("reportCnNumber", ""),
            "formulation_unit": d.get("formulationUnit", ""),
            "enable_type": d.get("enableType", ""),
            "publish_date": d.get("publishDate", ""),
            "administration_date": d.get("administrationDate", ""),
            "format": d.get("format", ""),
            "preview_url": d.get("url", ""),
        }

    # -------------------- 正文提取（WPS 预览渲染） --------------------
    # WPS 预览正文容器：多页文件按页平铺，只渲染视口附近页
    _SCROLL_SELECTOR = ".is-horizontal-scroll"
    _TIER_SELECTOR = ".uil-monitor-tier"

    def fetch_full_text(self, preview_url):
        """打开 WPS 在线预览，滚动遍历每页并拼接完整正文。

        WPS 虚拟渲染：DOM 只保留视口附近页。需按每页高度(~1000px)步进
        滚动，采集每步 tier 文本，用页码标记 '—N—' 拆块、按页码去重，
        最后按页码排序拼接出全文。
        """
        self._start()
        page = self._page
        page.goto(preview_url, wait_until="domcontentloaded", timeout=60000)

        # 等 WPS JS 初始化，并等 scrollHeight 稳定（懒加载完整页数）
        scroller = None
        deadline = time.time() + self.wait_render + 15
        last_h = -1
        stable_count = 0
        while time.time() < deadline:
            time.sleep(2)
            try:
                scroller = page.query_selector(self._SCROLL_SELECTOR)
                tier = page.query_selector(self._TIER_SELECTOR)
                if scroller and tier:
                    h = scroller.evaluate("el => el.scrollHeight")
                    if h == last_h:
                        stable_count += 1
                    else:
                        stable_count = 0
                    last_h = h
                    # scrollHeight 稳定且已有正文内容
                    if stable_count >= 2 and len(tier.inner_text() or "") > 100:
                        break
            except Exception:
                pass
        text = ""
        max_scroll = last_h if last_h > 0 else 0
        if scroller and max_scroll:
            pages = {}  # 页码 -> 文本
            for pos in range(0, int(max_scroll) + 1, 800):
                try:
                    page.eval_on_selector(
                        self._SCROLL_SELECTOR, f"el => {{ el.scrollTop = {pos} }}")
                except Exception:
                    break
                time.sleep(0.8)
                try:
                    tier = page.eval_on_selector(
                        self._TIER_SELECTOR, "el => el.innerText") or ""
                except Exception:
                    tier = ""
                # 按页码标记拆块。两种 WPS 预览器标记格式不同：
                #   条例站: —N—（全角破折号）；有限空间站: -N-（半角连字符，行首）。
                # 标记在行首，先按行首匹配；无行首标记（如破折号混在行内）再退化。
                # 避免误拆 "2025-01-26" 这类日期（其连字符不在行首）。
                parts = re.split(r"(?m)^[—\-]\s*(\d+)\s*[—\-](?=\n|$)", tier)
                if len(parts) == 1:
                    parts = re.split(r"—\s*(\d+)\s*—", tier)
                for i in range(1, len(parts), 2):
                    pageno = int(parts[i])
                    seg = parts[i + 1].strip() if i + 1 < len(parts) else ""
                    if seg and (pageno not in pages
                                or len(seg) > len(pages.get(pageno, ""))):
                        pages[pageno] = seg
            text = "\n".join(pages[k] for k in sorted(pages))

        # 兜底：CloudWAF 偶发把预览降级为纯文本渲染（无 .is-horizontal-scroll
        # 容器，正文逐字符换行），此时 scroll 模式取不到文本。改从 body 提取：
        # 去换行还原字符 → 按 -N- 分页 → 去尾部水印。
        if len(text) < 100:
            body = (page.evaluate(
                "() => document.body ? document.body.innerText : ''") or "")
            if body:
                flat = body.replace("\n", "")
                # 去掉 WPS 水印/占位垃圾（"mmm…lli" 簇或私有区字符）
                flat = re.sub(r"m{4,}lli.*$", "", flat)
                flat = re.sub(r"[-].*$", "", flat)
                # 去掉"附则X"这类分页占位伪影（X 紧跟 -N- 标记）
                flat = re.sub(r"X(?=-[0-9]+-)", "", flat)
                # 按 -N- / —N— 分页（(?<!\d) 避免误拆 "2025-01-26" 类日期；
                # .doc 老格式预览用全角破折号 —N—，.docx 用半角 -N-）
                parts = re.split(r"(?<!\d)[—-](\d+)[—-](?!\d)", flat)
                pages = {}
                for i in range(1, len(parts), 2):
                    pageno = int(parts[i])
                    seg = parts[i + 1].strip() if i + 1 < len(parts) else ""
                    if seg and (pageno not in pages
                                or len(seg) > len(pages.get(pageno, ""))):
                        pages[pageno] = seg
                if pages:
                    text = "\n".join(pages[k] for k in sorted(pages))
        return text

    # -------------------- 主流程 --------------------
    def fetch(self, keyword, file_type=2, output_dir=None):
        """
        按关键词抓取四川省级规章，返回标准 JSON dict。
        file_type: 2=政府规章（默认）/ 1=地方性法规
        """
        self._start()
        try:
            recs = self.search(keyword, file_type=file_type)
            if not recs:
                raise RuntimeError(f"四川库未检索到「{keyword}」(type={file_type})")

            # 取标题关键词重合最多的记录
            best = max(recs, key=lambda r: self._relevance(r["title"], keyword))
            print(f"  命中: {best['title']} ({best['formulationUnit']})")
            meta = self.detail(best["fileDataId"])
            if not meta["preview_url"]:
                raise RuntimeError(f"记录无正文预览链接: {best['title']}")

            print("  ⏳ 正在打开 WPS 预览渲染正文（约 15s）...")
            raw = self.fetch_full_text(meta["preview_url"])
            if not raw:
                raise RuntimeError("WPS 预览未渲染出正文")

            full_text = self._clean_wps_text(raw)

            _SXX_TEXT = {"3": "已修改", "2": "现行有效", "4": "已废止"}
            return {
                "title": meta["title"] or best["title"],
                "doc_no": meta["doc_no"],
                "category": "政府规章" if file_type == 2 else "地方性法规",
                "source": "rhpt.scspc.gov.cn",
                "source_url": ("https://rhpt.scspc.gov.cn/flfgkgzd/gov"
                               if file_type == 2 else
                               "https://rhpt.scspc.gov.cn/flfgkgzd/local"),
                "publish_date": meta["publish_date"],
                "effective_date": meta["administration_date"],
                "status": _SXX_TEXT.get(str(meta["enable_type"]), ""),
                "formulation_unit": meta["formulation_unit"],
                "chapters": split_law_text(full_text),
                "full_text": full_text,
            }
        finally:
            self._close()

    @staticmethod
    def _relevance(title, keyword):
        """标题关键词重合度：关键词全含优先。"""
        if keyword in title:
            return 1000 - len(title)
        return -abs(len(title) - len(keyword))

    @staticmethod
    def _clean_wps_text(raw):
        """清洗 WPS 预览渲染的正文。

        WPS 预览文本特点：
        - 每页有页码页眉："—\n1\n—" 或 "—1—"
        - docx 按页折行，中文可能被拆成两行（"安全生\n产事故"）
        - 页面边界处章/条标题与正文被压成一行（"…附则第一章总则第一条为了…"）
        - 可能带"大纲/暂未设置标题"等工具栏文字、"目录"段
        """
        import re as _re
        t = raw
        # 1. 去掉孤立页码（"—1—"、"—\n1\n—"、独立数字行）
        t = _re.sub(r'—\s*\d+\s*—', '', t)
        t = _re.sub(r'^\s*\d+\s*$', '', t, flags=_re.MULTILINE)
        # 2. 去掉 WPS 工具栏噪音
        for noise in ("大纲", "暂未设置标题", "未保存此页面", "加载中"):
            t = t.replace(noise, "")
        #    降级纯文本渲染会把预览器页脚也灌进正文，如"页码 : 1页面 : 1/16100%"
        t = _re.sub(r'页码\s*[:：]\s*\d+\s*页面\s*[:：]\s*\d+/\d+\s*100%', '', t)
        t = _re.sub(r'页码\s*[:：]\s*\d+', '', t)
        # 3. 合并跨行折行：中文字符间的换行直接拼接（不含标点）
        t = _re.sub(r'(?<=[一-鿿])\n(?=[一-鿿])', '', t)
        # 4. 先删目录段：WPS 目录是"目录第一章…第七章附则"，可能跨页换行。
        #    用 DOTALL 跨行匹配，以目录末尾"附则"（其后紧跟真正的"第一章…"）
        #    作为目录结束信号，整段删掉，正文从"第一章总则…"开始。
        m = _re.search(r'目录[\s\S]*?附则(?=\s*[第一二三四五六七八九十百千万零〇0-9０-９]*章|$)',
                       t)
        if m:
            t = t[:m.start()] + t[m.end():]
        else:
            # 兜底：目录未以附则结尾，退化为逐章删除目录项
            m = _re.search(r'目录(第[一二三四五六七八九十百千万零〇0-9０-９]+章[^第\n]{2,15}){2,}',
                           t)
            if m:
                t = t[:m.start()] + t[m.end():]
        # 5. 重建章/条换行结构：WPS 把短段落压成一行，降级纯文本渲染时更是
        #    整篇正文连成一行，需按三类位置插回换行。
        #    a) 章标题前换行（页边界/段落粘连，如"…的。第二章…"）。句中
        #       "依照本办法第三章的规定"这类引用前置动词/名词，前置非句号，
        #       不受影响（章引用的格式多为"第X章+名词"，前置是"照/据/按"）。
        t = _re.sub(r'(?<!^)(第[一二三四五六七八九十百千万零〇0-9０-９]+章)',
                    r'\n\1', t, flags=_re.MULTILINE)
        #    b) "章标题+该章第一条"压在同一行 → 在首条前换行
        #       （如"第二章生产经营单位的安全生产保障第十五条生产经营单位应当…"）
        t = _re.sub(
            r'(第[一二三四五六七八九十百千万零〇0-9０-９]+章[^\n]*?)'
            r'(第[一二三四五六七八九十百千万零〇0-9０-９]+条)',
            r'\1\n\2', t)
        #    c) 条标题前换行（"…的。第十五条…"；句中"未按照第二十三条…"
        #       前置是动词/名词，非句号，不受影响）
        t = _re.sub(r'(?<=[。；])(第[一二三四五六七八九十百千万零〇0-9０-９]+条)',
                    r'\n\1', t)
        # 6. 交给通用清洗（压缩空白）
        t = clean_text(t)
        return t
