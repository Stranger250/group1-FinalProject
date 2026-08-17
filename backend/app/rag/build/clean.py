"""清洗层：raw JSON → 清洗后 dict（对齐 docs/数据格式与建库注意事项.md §5）。

十项处理：no→article_no、status 三态归一化、doc_no 空兜底"-"、effective_date 空←publish_date、
title strip、formulation_unit 判空（存而不报错）、parse_error 丢弃、doc_id 静态映射、version 推导、过期清单。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# doc_id 静态映射（RAG 方案 §1.1，键 = 清洗后 title，全库唯一前缀）
DOC_ID_MAP: dict[str, str] = {
    "中华人民共和国公路法": "gl",
    "中华人民共和国安全生产法": "aqscf",
    "中华人民共和国建筑法": "jzf",
    "中华人民共和国消防法": "xf",
    "中华人民共和国突发事件应对法": "sjfa",
    "中华人民共和国职业病防治法": "zyf",
    "中华人民共和国行政处罚法": "xzcf",
    "中华人民共和国行政强制法": "xzqz",
    "中华人民共和国道路交通安全法": "djfa",
    "中华人民共和国道路运输条例": "dl",
    "四川省《中华人民共和国道路交通安全法》实施办法": "scdj",
    "四川省地质灾害防治条例": "scdz",
    "四川省安全生产条例": "scaq",
    "四川省有限空间作业安全管理规定": "scyx",
    "四川省消防条例": "scxf",
    "四川省生产安全事故报告和调查处理规定": "scbg",
    "四川省生产经营单位安全生产责任规定": "sczr",
    "四川省突发事件应对办法": "sctf",
    "四川省道路交通安全责任制规定": "scjl",
    "四川省道路运输条例": "scdl",
    "四川省高速公路条例": "scgs",
    "地质灾害防治条例": "dzh",
    "安全生产违法行为行政处罚办法": "wzcf",
    "工伤保险条例": "gs",
    "建设工程安全生产管理条例": "jsgc",
    "特种设备安全监察条例": "tsb",
    "生产安全事故应急预案管理办法": "yjfa",
    "生产安全事故报告和调查处理条例": "bgcd",
}

# status → 三态（数据里出现 "" / "有效" / "现行有效" / "已修改"）
_STATUS_NORMALIZE: dict[str, str] = {
    "": "现行有效",
    "有效": "现行有效",
    "现行有效": "现行有效",
    "已修改": "已修改",
    "已废止": "已废止",
}

# 版本疑似过期的法规（数据格式文档 §4.2，需人工核实修订/废止后走增量更新）
STALE_LAW_FLAGS: tuple[str, ...] = (
    "四川省消防条例",             # status=已修改（2011 生效）
    "四川省生产经营单位安全生产责任规定",  # 2007 生效
    "四川省突发事件应对办法",       # 2012 生效
)

# doc_level：效力数值编码（RAG 方案 §0.4；部门规章与地方性法规同位阶）
_CATEGORY_LEVEL: dict[str, int] = {
    "法律": 5,
    "行政法规": 4,
    "部门规章": 3,
    "地方性法规": 3,
    "政府规章": 2,
}

_DATE_YEAR_RE = re.compile(r"(19|20)\d{2}")


@dataclass
class CleanedDoc:
    """清洗后单篇法规（结构化，供 parser 消费）。"""
    title: str
    doc_id: str
    doc_no: str
    category: str
    doc_level: int
    region: str
    source_url: str
    publish_date: str
    effective_date: str
    status: str
    version: str
    is_latest: bool = True
    chapters: list = field(default_factory=list)  # [{chapter, articles:[{article_no, content}]}]
    doc_type: str = "法规"  # O4 六类：law/regulation/company/sop/plan/case（缺省「法规」兼容旧语料）


def normalize_status(raw: str) -> str:
    return _STATUS_NORMALIZE.get(raw.strip(), "已废止")


def derive_version(date_str: str) -> str:
    """从日期取年份 → v2023；无日期兜底 v1。"""
    m = _DATE_YEAR_RE.search(date_str or "")
    return f"v{m.group(0)}" if m else "v1"


def clean_doc(raw: dict, source_filename: str = "") -> CleanedDoc:
    title = (raw.get("title") or "").strip()
    if not title:
        raise ValueError(f"title 为空（文件 {source_filename}）")
    # DOC_ID_MAP 命中用静态映射（既有 28 部）；未命中自动生成确定性 doc_id（O4 新增六类语料）
    doc_id = DOC_ID_MAP.get(title) or f"d{hashlib.md5(title.encode('utf-8')).hexdigest()[:10]}"

    category = (raw.get("category") or "").strip() or "法规"
    doc_level = _CATEGORY_LEVEL.get(category, 3)
    # region：显式字段 > doc_id 前缀推断 > 国家
    region = (raw.get("region") or "").strip() or ("四川" if doc_id.startswith("sc") else "国家")
    publish_date = (raw.get("publish_date") or "").strip()
    effective_date = (raw.get("effective_date") or "").strip() or publish_date
    doc_no = (raw.get("doc_no") or "").strip() or "-"
    doc_type = (raw.get("doc_type") or "").strip() or "法规"

    chapters = []
    for ch in raw.get("chapters") or []:
        articles = [
            {
                "article_no": (a.get("no") or "").strip(),
                "content": (a.get("content") or "").strip(),
            }
            for a in ch.get("articles") or []
        ]
        articles = [a for a in articles if a["article_no"] and a["content"]]
        chapters.append({"chapter": (ch.get("chapter") or "").strip(), "articles": articles})

    return CleanedDoc(
        title=title,
        doc_id=doc_id,
        doc_no=doc_no,
        category=category,
        doc_level=doc_level,
        region=region,
        source_url=(raw.get("source_url") or "").strip(),
        publish_date=publish_date,
        effective_date=effective_date,
        status=normalize_status(raw.get("status") or ""),
        version=derive_version(effective_date or publish_date),
        chapters=chapters,
        doc_type=doc_type,
    )
