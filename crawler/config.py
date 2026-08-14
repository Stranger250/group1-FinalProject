# -*- coding: utf-8 -*-
"""
爬虫全局配置：UA 池、限速、重试、输出目录、正文容器选择器。
所有值都放在这里，改配置不用改代码。
"""
import os

# ===================== 输出目录 =====================
# 输出根 = shudao/crawler_output（与爬虫目录同级）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "crawler_output")

# ===================== 请求基础参数 =====================
REQUEST_INTERVAL = 1.5   # 两次请求最小间隔（秒），防 IP 封禁
REQUEST_RETRIES = 3      # 失败重试次数（指数退避）
REQUEST_TIMEOUT = 20     # 单次请求超时（秒）
MAX_REQUESTS_PER_RUN = 30  # 单来源单次运行请求总量上限（合规保护）

# 桌面浏览器 UA 池（政府站常校验 UA）
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/126.0.0.0 Safari/537.36",
]

# ===================== 通道A：flk 国家法律法规库 =====================
FLK_BASE = "https://flk.npc.gov.cn"
FLK_DEFAULT_FORMAT = "docx"  # docx 优先；pdf 缺失时自动回退 docx

# ===================== 通道B：moj 国家行政法规库 =====================
MOJ_BASE = "http://xzfg.moj.gov.cn"
# 详情页正文容器选择器（⚠️ 未实证，需 --probe 验证后调整）
MOJ_CONTENT_SELECTORS = [
    ".law-content", ".lawContent", "#lawContent",
    ".content", "#content", ".detail-content", ".article", "article",
]

# ===================== 通道C：国务院政策文件库 =====================
GOV_API = "https://sousuo.www.gov.cn/search-gov/data"
# 政策文件库正文页(.htm)容器选择器（⚠️ 未实证）
GOV_CONTENT_SELECTORS = [
    ".pages_content", ".content", "#content", ".article",
    ".TRS_Editor", ".UCAP-CONTENT", "article",
]
