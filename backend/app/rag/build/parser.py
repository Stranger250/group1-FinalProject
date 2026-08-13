"""解析层：清洗后 dict → 原子块（章/条）+ 长条父子块 + 打标。

契约（RAG 方案 §0.2 / §1.3）：
  - 第X条 = 1 父块（2087 个）；章头辅助块 199 个；
  - 条长 >400 字才二次分块，按句（。；、）切子块，100-250 字/块，相邻重叠 1 句；
  - 子块 ID = {父块id}_s{seq}；章头 ID = {doc_id}_chapter{序号}_v{ver}；
  - difficulty / domain_tags 离线预计算入 metadata（契约 §4.3 / §2.5.1）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .clean import CleanedDoc

# 效力层级/区域/类型常量（MVP 全公开法规）
ACCESS_LEVEL = "公开"
DOC_TYPE = "法规"


@dataclass
class Block:
    """向量库/MySQL 的最小落库单元（父子块同构）。"""
    chunk_id: str
    doc_id: str
    title: str
    doc_no: str
    category: str
    doc_level: int
    region: str
    chapter: str
    article_no: str            # "第X条"；章头块为 ""
    content: str
    is_parent: bool
    parent_id: str             # 父块 chunk_id（父块即自身）
    seq: int
    status: str
    publish_date: str
    effective_date: str
    version: str
    is_latest: bool
    source_url: str
    ref_out: list[str] = field(default_factory=list)
    domain_tags: list[str] = field(default_factory=list)
    difficulty: str = "easy"
    access_level: str = ACCESS_LEVEL
    doc_type: str = DOC_TYPE
    # 落库后回填的自增主键（loader 阶段赋值）
    db_doc_id: int | None = None
    db_chunk_id: int | None = None
    parent_db_chunk_id: int | None = None

    def meta_snapshot(self) -> dict:
        """元数据 Schema（契约 §0.3），Chroma 落库用。ref_out/domain_tags JSON 编码。"""
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title": self.title,
            "doc_no": self.doc_no,
            "category": self.category,
            "doc_level": self.doc_level,
            "region": self.region,
            "chapter": self.chapter,
            "article_no": self.article_no,
            "content": self.content,
            "is_parent": self.is_parent,
            "parent_chunk_id": self.parent_id,
            "status": self.status,
            "publish_date": self.publish_date,
            "effective_date": self.effective_date,
            "version": self.version,
            "is_latest": self.is_latest,
            "ref_out": json.dumps(self.ref_out, ensure_ascii=False),
            "domain_tags": json.dumps(self.domain_tags, ensure_ascii=False),
            "difficulty": self.difficulty,
            "doc_type": self.doc_type,
            "access_level": self.access_level,
            "source_url": self.source_url,
            # 检索端直出 int 主键（G3 关键：message_source 逻辑外键回填）
            "db_doc_id": self.db_doc_id,
            "db_chunk_id": self.db_chunk_id,
            "parent_db_chunk_id": self.parent_db_chunk_id,
        }


# ---------- 分句 / 子块 ----------

_SENT_SPLIT_RE = re.compile(r"(?<=[。；！？])|(?<=[。；])(?=\S)")


def split_sentences(text: str) -> list[str]:
    """按句切分，保留句末标点；忽略空串。"""
    parts = [p.strip() for p in re.split(r"(?<=[。；！？])", text) if p.strip()]
    return parts


def _split_child_blocks(content: str, parent_id: str, doc_id: str, version: str) -> list[Block]:
    """>400 字长条按句切子块：每组 100-250 字，相邻重叠 1 句（契约 §0.2）。"""
    from ...core.config import get_settings

    settings = get_settings()
    min_chars = settings.rag_child_min_chars
    max_chars = settings.rag_child_max_chars
    sents = split_sentences(content)
    children: list[Block] = []
    seq = 0
    start = 0
    n = len(sents)
    while start < n:
        end = start
        cur = ""
        while end < n:
            # 已满足下限且再加一句会超上限 → 收口
            if cur and len(cur) + len(sents[end]) > max_chars:
                break
            cur += sents[end]
            end += 1
            if len(cur) >= min_chars:
                break
        # 防死循环：单句超长（异常），强制纳入
        if end == start:
            end = start + 1
            cur = sents[start]
        seq += 1
        child_id = f"{parent_id}_s{seq}"
        child = Block(
            chunk_id=child_id, doc_id=doc_id, title="", doc_no="", category="",
            doc_level=0, region="", chapter="", article_no="", content=cur,
            is_parent=False, parent_id=parent_id, seq=0, status="", publish_date="",
            effective_date="", version=version, is_latest=True, source_url="",
        )
        children.append(child)
        # 重叠 1 句：下一窗口从当前最后一句开始
        start = end - 1 if end - 1 > start else end
    return children


# ---------- 打标 ----------

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "有限空间作业": ("有限空间", "受限空间", "缺氧", "中毒窒息"),
    "隧道施工": ("隧道", "衬砌", "掌子面"),
    "桥梁施工": ("桥梁", "高架"),
    "高边坡": ("高边坡", "边坡开挖", "边坡砌筑"),
    "地质灾害": ("地质灾害", "滑坡", "泥石流", "崩塌", "地灾"),
    "事故报告": ("事故报告", "报告事故", "瞒报", "谎报", "迟报"),
    "事故调查": ("事故调查", "调查处理", "责任追究"),
    "道路运输": ("道路运输", "营运车辆", "客货运输"),
    "高速公路": ("高速公路", "高速", "收费站", "匝道"),
    "消防安全": ("消防", "火灾", "灭火", "防火"),
    "职业健康": ("职业病", "劳动防护", "防护用品", "健康检查"),
    "应急管理": ("应急预案", "应急演练", "应急救援", "突发事件"),
    "安全责任": ("安全生产责任", "责任制", "主要负责人", "安全管理机构"),
    "道路交通安全": ("道路交通", "道交", "交通事故", "通行"),
    "特种设备": ("特种设备", "起重", "压力容器", "锅炉", "电梯"),
    "行政处罚": ("行政处罚", "罚款", "责令停产", "吊销", "拘留"),
}


def compute_domain_tags(content: str) -> list[str]:
    tags = [tag for tag, kws in _DOMAIN_KEYWORDS.items() if any(k in content for k in kws)]
    return sorted(set(tags))


_PENALTY_KW = ("罚款", "责令停产", "停业", "吊销", "拘留", "万元", "没收")
_NUM_UNIT_RE = re.compile(r"[0-9０-９]+(?:日|天|月|年|小时|倍|%|％|元|万元|人次|个|次)")


def compute_difficulty(content: str, ref_count: int) -> str:
    """规则难度评分器（契约 §4.3）：0=简单 / 1=中等 / ≥2=困难。"""
    score = 0
    if any(k in content for k in _PENALTY_KW):
        score += 1
    if _NUM_UNIT_RE.search(content):
        score += 1
    if content.count("；") >= 3:
        score += 1
    if ref_count >= 2:
        score += 1
    if len(content) > 300:
        score += 1
    if score == 0:
        return "easy"
    if score == 1:
        return "medium"
    return "hard"


# ---------- 主解析 ----------

def parse_doc(doc: CleanedDoc, warn_dup: bool = True) -> list[Block]:
    """清洗后单篇法规 → 原子块列表（章头块 + 父块 + 超长子块）。

    数据质量：源数据存在重复条号（实测四川省生产经营单位安全生产责任规定有两个
    "第十七条"），chunk_id 追加 `_2` 后缀保证唯一（幂等 upsert 依赖），不改源文件，
    仅打印告警供人工修正源数据。
    """
    import logging

    logger = logging.getLogger("rag.build.parser")
    blocks: list[Block] = []
    seq = 0
    seen_article_no: set[str] = set()
    used_chunk_ids: set[str] = set()
    for ch_idx, ch in enumerate(doc.chapters, start=1):
        chapter_name = ch["chapter"]
        seq += 1
        chapter_block = Block(
            chunk_id=f"{doc.doc_id}_chapter{ch_idx}_{doc.version}",
            doc_id=doc.doc_id, title=doc.title, doc_no=doc.doc_no,
            category=doc.category, doc_level=doc.doc_level, region=doc.region,
            chapter=chapter_name, article_no="", content=chapter_name,
            is_parent=True, parent_id=f"{doc.doc_id}_chapter{ch_idx}_{doc.version}",
            seq=seq, status=doc.status, publish_date=doc.publish_date,
            effective_date=doc.effective_date, version=doc.version,
            is_latest=doc.is_latest, source_url=doc.source_url,
            domain_tags=compute_domain_tags(chapter_name),
        )
        blocks.append(chapter_block)

        for art in ch["articles"]:
            article_no = art["article_no"]
            content = art["content"]
            seq += 1
            # 重复条号确定性去重（首个不加后缀，后续 _dup2/_dup3…）
            if article_no in seen_article_no:
                dup_no = 2
                parent_id = f"{doc.doc_id}_{article_no}_dup{dup_no}_{doc.version}"
                while parent_id in used_chunk_ids:
                    dup_no += 1
                    parent_id = f"{doc.doc_id}_{article_no}_dup{dup_no}_{doc.version}"
                if warn_dup:
                    logger.warning(
                        "数据质量：%s 存在重复条号 %s（第 %d 次出现，chunk_id=%s）",
                        doc.title, article_no, dup_no, parent_id,
                    )
            else:
                seen_article_no.add(article_no)
                parent_id = f"{doc.doc_id}_{article_no}_{doc.version}"
            used_chunk_ids.add(parent_id)
            parent = Block(
                chunk_id=parent_id, doc_id=doc.doc_id, title=doc.title,
                doc_no=doc.doc_no, category=doc.category, doc_level=doc.doc_level,
                region=doc.region, chapter=chapter_name, article_no=article_no,
                content=content, is_parent=True, parent_id=parent_id, seq=seq,
                status=doc.status, publish_date=doc.publish_date,
                effective_date=doc.effective_date, version=doc.version,
                is_latest=doc.is_latest, source_url=doc.source_url,
            )
            blocks.append(parent)

            if len(content) > 400:
                for child in _split_child_blocks(content, parent_id, doc.doc_id, doc.version):
                    seq += 1
                    child.seq = seq
                    # 子块继承父块元数据（除内容/父指针）
                    child.title = doc.title
                    child.doc_no = doc.doc_no
                    child.category = doc.category
                    child.doc_level = doc.doc_level
                    child.region = doc.region
                    child.chapter = chapter_name
                    child.article_no = article_no
                    child.status = doc.status
                    child.publish_date = doc.publish_date
                    child.effective_date = doc.effective_date
                    child.is_latest = doc.is_latest
                    child.source_url = doc.source_url
                    blocks.append(child)
    return blocks


def tag_blocks(blocks: list[Block]) -> None:
    """打标：difficulty 在 ref_out 确定后调用（需 ref_count）；子块继承父块难度。"""
    parent_difficulty: dict[str, str] = {}
    for b in blocks:
        if not b.domain_tags:
            b.domain_tags = compute_domain_tags(b.content)
        if b.is_parent and b.article_no:  # 难度只在完整条文上评，不评碎片
            b.difficulty = compute_difficulty(b.content, len(b.ref_out))
            parent_difficulty[b.chunk_id] = b.difficulty
    for b in blocks:
        if not b.is_parent:
            b.difficulty = parent_difficulty.get(b.parent_id, "easy")
