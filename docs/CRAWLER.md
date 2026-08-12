# 规章爬虫 · 实现说明

蜀道安全助手 **考试工坊（E02 AI 出题）** 的规章数据来源。从 0 抓取公开安全生产规章，输出结构化 JSON（标题/文号/章节/条款/元数据/来源URL），供后续 RAG 知识库建库、AI 出题引用原文。需求依据见 `docs/PRD.md`（A01 知识库范围 / E02 AI 出题）。

- 代码目录：`crawler/`
- 输出目录：`crawler_output/`（每部规章一个 JSON + `index.json` 索引）
- 批量清单：`crawler/targets.json`

## 快速开始

```bash
cd d:\code\2026\7_8月实训\shudao

# 1. 依赖（首次）
pip install -r requirements.txt          # requests bs4 lxml pdfplumber python-docx

# 2. 探测模式：确认接口/页面结构（不落盘，调试用）
python crawler/main.py --probe --source flk --keyword 中华人民共和国安全生产法

# 3. 单条抓取
python crawler/main.py --source flk --keyword 中华人民共和国安全生产法
python crawler/main.py --source dept --keyword 生产安全事故应急预案管理办法 --department 应急管理部

# 4. 按清单批量（断点续爬：已存在的自动跳过，--force 覆盖）
python crawler/main.py --targets crawler/targets.json
```

> Windows 控制台是 GBK：所有入口脚本开头已 `sys.stdout.reconfigure(encoding="utf-8")`，乱码可检查是否由此引起。

## 四通道总览

| 通道 | 站点 | 类型 | 正文获取 | 已实测 |
| --- | --- | --- | --- | --- |
| A `flk` | 国家法律法规库 `flk.npc.gov.cn` | 法律 + 部分行政法规 | JSON API → docx → 解析 | ✅ 14部 |
| B `moj` | 国家行政法规库 `xzfg.moj.gov.cn` | 行政法规 | HTML 服务端渲染 | ✅ 1部 |
| C `dept` | 国务院政策文件库（聚合各部委规章） | 部门规章 | JSON API 搜索 → 静态页 HTML | ✅ 2部 |
| D `sichuan` | 四川法规规章库 `rhpt.scspc.gov.cn` | 四川地方性法规/政府规章 | playwright + WPS 在线预览渲染 | ✅ 11部 |

全部限速 ≥1.5s、指数退避重试 3 次、尊重 robots.txt、单次运行请求上限 30（`config.MAX_REQUESTS_PER_RUN`）。

---

## 通道A：flk 国家法律法规库

**特性**：全站前端 SPA，HTML 里没有数据，必须走官方 JSON API。

### 接口（均已实证 2026-08）

| 用途 | 方法 | URL | 关键参数 |
| --- | --- | --- | --- |
| 搜索 | POST | `/law-search/search/list` | 见下方 body |
| 详情 | GET | `/law-search/search/flfgDetails` | `bbbs` |
| 下载 | GET | `/law-search/download/pc` | `format=docx\|pdf`、`bbbs` |

需带 `Referer: https://flk.npc.gov.cn/detail?id={bbbs}`。

搜索 body（JSON）：
```json
{
  "searchRange": 1,        // 1=标题检索，2=正文检索。必须是数字，传数组会 500
  "searchType": 2,         // 2=模糊
  "searchContent": "关键词",
  "orderByParam": {"order": "-1", "sort": ""},   // 必须 "-1"，升序会 500
  "pageNum": 1,
  "pageSize": 20
}
```

下载接口返回 `data.url` 为**带签名的 OSS 临时链接**（`flkoss.obs-bj2.cucloud.cn`），须即时消费，且：
- 签名 URL 会被本爬虫的 robots 检查误伤 → 下载走 `http.download()`（跳过 robots，仅限速）
- `format=pdf` 可能返回空 `data` → 代码自动回退 docx

### 正文解析
- docx → `python-docx` 提取段落 + 表格（部分法规条文在表格里）
- 解析失败不中断，保留 `parse_error` 字段；旧 `.doc` 格式 python-docx 不认

### 元数据字段（宽松匹配）
详情响应嵌套在 `data` / `data.flfg` 里。已证实的字段映射：
- `title`、`whao`(文号)、`flxz`(分类)、`gbrq`(公布)、`sxrq`(施行)、`sxx`(时效数字)
- 时效 `sxx` 为数字：`1=已废止 / 2=已修改 / 3=现行有效 / 4=尚未生效`（`_SXX_TEXT` 映射）

### 脆弱点
- **接口随前端改版可能失效**，字段名要以 `--probe` 实测为准
- `searchRange`、`orderByParam` 参数值有坑（数组/升序都 500）
- 搜索结果 title 带 `<em class='highlight'>` 高亮标签，已用 `_clean_title()` 处理
- 法律类（如安全生产法）没有"主席令第X号"文号，题注是"××年×月×日通过…修正"格式，`doc_no` 为空属正常
- IP 频率限制 → 已限速+重试；换大量数据建议分批跑

---

## 通道B：moj 国家行政法规库

**特性**：服务端渲染 HTML，可直接抓。

### 接口（均已实证 2026-08）

| 用途 | URL | 关键参数 |
| --- | --- | --- |
| 搜索 | `http://xzfg.moj.gov.cn/SearchAdvancedFront` | **`title`**（不是 keyword，表单字段名就是 title） |
| 详情 | `http://xzfg.moj.gov.cn/front/law/detail` | `LawID` |

### 正文提取
正文容器 class **已实测为 `.law-chapter`**（页面 h2 全是章节标题，法规名不在 h1/h2 里）。
选择器链：`.law-chapter` → `.law-content` → 兜底去 script/style/nav 取 `<body>` 文本。

### 脆弱点
- **法规名不在标题标签里** → `_extract_title()` 从正文第一行非"第X章"的行猜法规名；更稳的是用搜索结果里的标题（`fetch_by_id(law_id, fallback_title=...)`）
- 搜索页有下载链接等噪音链接，`search()` 用 `LawID= && download 不在 href` 过滤
- LawID 不保证连续，不要用遍历猜 ID；从搜索页拿

---

## 通道C：dept 部门规章（国务院政策文件库）

**特性**：政策文件库 API 聚合了各部委规章（应急管理部/交通运输部等），比逐站爬 mem/mot 稳得多，是首选。代码里没有实现 mem/mot 直爬兜底（选择器未实证，如需要再补）。

### 接口（均已实证 2026-08）

| 用途 | 方法 | URL | 关键参数 |
| --- | --- | --- | --- |
| 搜索 | GET | `https://sousuo.www.gov.cn/search-gov/data` | 见下方 params |
| 正文 | GET | 搜索结果里的 `url` 字段（静态 `.htm`） | — |

搜索 params：
```python
{
  "t": "zhengcelibrary",       # 固定
  "q": "关键词",
  "searchfield": "title",      # 标题检索；content 会混入大量正文命中
  "sort": "score", "sortType": 1,
  "p": 0, "n": 20,
  "type": "gwyzcwjk",          # 固定
  # 部委过滤（可选，加快精准度）：
  "childtype": "bumenfile",
  "bmfl": "应急管理部",
}
```

**响应结构**（关键坑）：
- 列表**不在** `data` 字段（`data` 恒为 null），在 `searchVO.catMap.<分类>.listVO`，需把所有分类的 `listVO` 展平
- `searchVO.totalCount` 恒为 0，**不能用它判断是否有结果**
- 记录里的正文链接在 **`url`** 字段（`piclinksurl`/`pcode` 常为空）
- 记录 title 带 `<em>`/`<br>` 标签、全角空格，如 `国家安全生产监督管理总局令（第88号）　　生产安全事故应急预案管理办法`
- 时间在 `pubtimeStr`（如 `2016.10.10`）

### 标题拆分 `_split_title`
`XX令（第X号）　　法规名` → 拆成 `doc_no=XX令（第X号）`、`title=法规名`。
- 站点后缀 `__2016年第28号国务院公报_中国政府网` 会被剥掉
- 正则：`^[^（]*令（第[一二三四五六七八九十0-9]+号）$`（注意 `endswith('令')` 不行，首段结尾是 `号）`）

### 脆弱点
- **gov.cn 部分页面 HTML 标签不闭合，lxml 会把 DOM 解析坏**（正文容器直接消失，只剩 header 导航）→ `fetch_article()` 用 lxml + html.parser 各解析一次，**取文本更长的结果**
- 正文容器 `.pages_content`（公报页）；普通页还有 `.TRS_Editor`、`.UCAP-CONTENT` 等（选择器已列在 config，未逐一实测）
- 搜索结果可能混入相近文件 → `_relevance()` 按标题关键词重合度选最佳记录

---

## 通道D：sichuan 四川省法规规章规范性文件数据库

**特性**：省人大常委会主办的全文数据库（`rhpt.scspc.gov.cn`），收录四川地方性法规 + 省政府规章，是蜀道项目本地法规的主来源。**前置 Next.js + CloudWAF，纯 requests 会被 WAF 拦截（返回 304 空 body），必须用 playwright 起真实 Chromium**：

```bash
pip install playwright
python -m playwright install chromium   # 慢就加 PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
```

### 接口（均已实证 2026-08，浏览器页面内 fetch 调用）

| 用途 | 方法 | URL | 关键参数 |
| --- | --- | --- | --- |
| 列表 | GET | `/flfgkgzd/publicPlatform/typeSearch` | `content`(关键词)、`type`(2=政府规章/1=地方性法规)、`pageNum`/`pageSize`、`enableType`(2=现行有效) |
| 详情 | GET | `/flfgkgzd/publicPlatform/info` | `fileDataId` |
| 正文 | — | 详情 `url` 字段 → `wps.scspc.gov.cn` 在线预览 | playwright 滚动渲染 |

列表响应 `data.rows[]` 字段：`fileDataId`/`fileTitle`/`formulationUnit`/`enableType`/`publishDate`。
详情响应 `data.data` 字段：`fileTitle`/`reportCnNumber`(文号)/`formulationUnit`/`enableType`/`publishDate`/`administrationDate`/`format`/`url`(WPS预览链接)。

### ⚠️ CloudWAF 降级（最重要的坑）

**不能用 playwright 的 `context.request.get()` 调接口** —— 那会触发 CloudWAF，把**后续 WPS 预览降级成纯文本渲染**（正文逐字符换行、没有 `.is-horizontal-scroll` 容器、页码标记格式变化）。降级是**由请求触发、不可预测**的。规避办法：先导航到 rhpt 站内页，再用 `page.evaluate` 在页面里 `fetch()` 调接口（`_api()`），走浏览器真实 JS 指纹，不触发降级。

### 正文提取（`fetch_full_text`）

WPS 预览虚拟渲染，DOM 只留视口附近页：
1. 等 `.is-horizontal-scroll` scrollHeight 稳定（懒加载）
2. 按 800px 步进滚动，采集每步 `.uil-monitor-tier` 文本
3. 按页码标记拆块（**两种格式**：条例站 `—N—` 全角破折号；有限空间站 `-N-` 半角连字符行首），按页码去重排序拼接
4. **降级兜底**：文本不足 100 字符时从 `document.body.innerText` 取全文 → 去换行还原字符 → 去掉 `X` 分页占位伪影（`X(?=-N-)`）→ 按 `-N-` 拆页 → 按页拼接

### 文本清洗（`_clean_wps_text`）

WPS 渲染的文本需要重建章/条结构，处理顺序：
1. 去孤立页码 `—1—`/独立数字行
2. 去工具栏噪音（大纲/暂未设置标题…）+ 降级页脚噪音（`页码 : 1页面 : 1/16100%`）
3. 合并跨行折行（中文字符间的 `\n` 直接拼）
4. 删目录段（`目录…附则` DOTALL 匹配，附则后紧跟真正的 `第X章`）
5. **重建章/条换行**（降级时整篇压成一行，靠三类位置插回 `\n`）：
   - `(?<!^)(第X章)` → 章前换行（页边界/段落粘连；句中"本办法第三章"这类引用前置名词不受影响）
   - `(第X章[^\n]*?)(第X条)` → 在首条前换行（章标题+首条粘连）
   - `(?<=[。；])(第X条)` → 条前换行（"…的。第十五条…"；句中"第二十三条"引用前置动词/名词不受影响）
6. 通用空白压缩

### 脆弱点
- **标题匹配**：搜索按关键词模糊匹配，可能混入市州规章 → `search()` 默认 `province_only` 只保留"四川省人民政府"（省级），`fetch()` 再按标题关键词重合度选最佳
- **降级不可预测**：同一部法规可能这次正常滚动、下次降级 → 两条路径都要能产出干净文本
- **WPS 预览器有两种标记格式**（`—N—` 与 `-N-`），拆页正则需兼容
- 每部法规抓取约 35s（浏览器启动 + 预览渲染），批量抓 8-10 部约 5 分钟

---

## 输出 JSON 结构

```json
{
  "title": "生产安全事故应急预案管理办法",
  "doc_no": "国家安全生产监督管理总局令（第88号）",
  "category": "部门规章",
  "source": "gov.cn 政策文件库",
  "source_url": "http://www.gov.cn/gongbao/content/2016/content_5115850.htm",
  "publish_date": "2016-10-10",
  "effective_date": "",
  "status": "",
  "chapters": [
    {"chapter": "第一章 总则", "articles": [
      {"no": "第一条", "content": "为规范生产安全事故应急预案管理工作，……"}
    ]}
  ],
  "full_text": "整篇纯文本（供 RAG 分块）"
}
```

- `chapters`：由 `core/splitter.py` 按 `第X章`/`第X条` 正则拆分；无章结构（如部分规章）会归入隐式"正文"章
- `full_text`：整篇纯文本，RAG 分块直接切它即可
- `doc_no`：行政法规是"国务院令第X号"，部门规章是"XX令（第X号）"，法律通常为空（无文号）

## 已抓取成果（2026-08-12，共 28 部：全国 17 + 四川 11）

### 国家层（flk 14 / moj 1 / dept 2，共 17 部）

| 规章 | 类别 | 文号 | 通道 | 规模 |
| --- | --- | --- | --- | --- |
| 中华人民共和国安全生产法 | 法律 | —（2021第三次修正） | flk | 7章 119条 |
| 中华人民共和国突发事件应对法 | 法律 | —（2024修订） | flk | 8章 106条 |
| 中华人民共和国道路交通安全法 | 法律 | —（2021修正） | flk | 8章 124条 |
| 中华人民共和国消防法 | 法律 | —（2021修正） | flk | 7章 74条 |
| 中华人民共和国职业病防治法 | 法律 | —（2018修正） | flk | 7章 88条 |
| 中华人民共和国公路法 | 法律 | —（2017修正） | flk | 9章 87条 |
| 中华人民共和国行政处罚法 | 法律 | —（2021修订） | flk | 8章 86条 |
| 中华人民共和国行政强制法 | 法律 | —（2011） | flk | 7章 71条 |
| 中华人民共和国建筑法 | 法律 | —（2019修正） | flk | 8章 85条 |
| 建设工程安全生产管理条例 | 行政法规 | 国务院令第393号 | flk | 8章 71条 |
| 特种设备安全监察条例 | 行政法规 | 国务院令第373号 | flk | 8章 103条 |
| 中华人民共和国道路运输条例 | 行政法规 | 国务院令第406号 | flk | 7章 82条 |
| 工伤保险条例 | 行政法规 | 国务院令第375号 | flk | 8章 67条 |
| 地质灾害防治条例 | 行政法规 | 国务院令第394号 | flk | 7章 49条 |
| 生产安全事故报告和调查处理条例 | 行政法规 | 国务院令第493号 | moj | 6章 46条 |
| 安全生产违法行为行政处罚办法 | 部门规章 | 应急管理部令（第18号） | dept | 6章 90条 |
| 生产安全事故应急预案管理办法 | 部门规章 | 安监总局令（第88号） | dept | 7章 48条 |

### 四川省级（sichuan，蜀道本地法规主来源，共 11 部）

| 规章 | 类型 | 规模 |
| --- | --- | --- |
| 四川省安全生产条例 | 地方性法规 | 7章 78条 |
| 四川省消防条例 | 地方性法规 | 8章 78条 |
| 四川省地质灾害防治条例 | 地方性法规 | 8章 65条 |
| 四川省高速公路条例 | 地方性法规 | 7章 63条 |
| 四川省道路运输条例 | 地方性法规 | 6章 70条 |
| 四川省《中华人民共和国道路交通安全法》实施办法 | 地方性法规 | 7章 77条 |
| 四川省生产经营单位安全生产责任规定 | 政府规章 | 5章 53条 |
| 四川省生产安全事故报告和调查处理规定 | 政府规章 | 6章 44条 |
| 四川省突发事件应对办法 | 政府规章 | 7章 60条 |
| 四川省道路交通安全责任制规定 | 政府规章 | 6章 64条 |
| 四川省有限空间作业安全管理规定 | 政府规章 | 6章 39条 |

> 合计：28 部 / 199 章 / 2087 条（全国 17 部 1396 条 + 四川 11 部 691 条），章/条逐部由脚本核验。
> 需求口径：PRD A01 知识库范围为本期 28 部公开安全生产法规；"企业安全管理制度/操作规程/事故案例"等内部文档属**扩展层**，不在公开网页上，爬虫无法获取，需人工整理后经管理后台上传导入（见 `docs/RAG优化方案.md` §1.5）。

## 合规说明
- 仅抓取公开政府规章文本（法律法规本应公开可查）
- 不绕验证码、不并发猛刷，限速 1.5s，尊重 robots.txt
- 仅用于培训项目学习研究，不商用
