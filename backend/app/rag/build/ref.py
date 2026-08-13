"""交叉引用扫描（172 处专项，契约 §0.5 / §1.2.3）。

两种引用形态（实测 28 部）：
  1. 跨法引用 《书名》第X条（18 处）——书名经别名表解析到 doc_id；
  2. 同法裸引用 第X条（154 处）——指代映射表「本法 → 当前 doc」解析到本文。
ref_out 只收录解析到库内目标的引用（`{doc_id}_{article_no}_{version}`）；
解析不到（库外/错别字）计入 unresolved，覆盖率 = resolved/172 ≥90% 作质量闸门。
"""
from __future__ import annotations

import re

from .clean import DOC_ID_MAP
from .parser import Block

_BOOK_RE = re.compile(r"《([^》]{1,40})》第([一二三四五六七八九十百零]+)条")
_BARE_RE = re.compile(r"第([一二三四五六七八九十百零]+)条")

# 覆盖率闸门（契约 §1.6 质量闸门；172 处中解析到库内目标的比例）
RESOLUTION_GATE = 0.90

# 书名别名表：全称 + 去「中华人民共和国 / 四川省」前缀的简称。
# setdefault 保证长名优先，短名冲突时先到先得（实测无冲突）。
_ALIASES: dict[str, str] = {}


def _build_aliases() -> dict[str, str]:
    if _ALIASES:
        return _ALIASES
    for title, doc_id in DOC_ID_MAP.items():
        _ALIASES[title] = doc_id
        for prefix in ("中华人民共和国", "四川省"):
            if title.startswith(prefix):
                short = title[len(prefix):]
                _ALIASES.setdefault(short, doc_id)
    return _ALIASES


def build_article_index(blocks_by_doc: dict[str, list[Block]]) -> dict[tuple[str, str], str]:
    """(doc_id, article_no) → 父块 chunk_id 索引（引用精确查回用）。"""
    idx: dict[tuple[str, str], str] = {}
    for doc_id, blocks in blocks_by_doc.items():
        for b in blocks:
            if b.is_parent and b.article_no:
                idx[(doc_id, b.article_no)] = b.chunk_id
    return idx


def scan_refs(
    blocks_by_doc: dict[str, list[Block]],
    article_index: dict[tuple[str, str], str],
    version_by_doc: dict[str, str],
) -> tuple[int, int, list[dict]]:
    """扫描全部父块内容引用，回填 ref_out。

    返回 (found, resolved, unresolved_samples)。found 应 = 172（实测口径）；
    unresolved_samples 每项 {doc_id, article_no, target_name, article_no_str, reason}。
    """
    aliases = _build_aliases()
    found = 0
    resolved = 0
    unresolved: list[dict] = []

    for doc_id, blocks in blocks_by_doc.items():
        # 本文条号集合（同法裸引用查回）
        own_articles = {ano for (d, ano) in article_index if d == doc_id}
        version = version_by_doc.get(doc_id, "v1")

        for b in blocks:
            if not (b.is_parent and b.article_no):
                continue
            content = b.content
            targets: list[str] = []

            # 1) 跨法 《书名》第X条
            for m in _BOOK_RE.finditer(content):
                found += 1
                name = m.group(1).strip()
                ano = f"第{m.group(2)}条"
                tdoc = aliases.get(name)
                if tdoc and (tdoc, ano) in article_index:
                    resolved += 1
                    targets.append(article_index[(tdoc, ano)])
                else:
                    unresolved.append({
                        "doc_id": doc_id, "article_no": b.article_no,
                        "target": f"《{name}》{ano}",
                        "reason": "书名未解析到库内目标" if tdoc else "书名不在别名表",
                    })

            # 2) 同法裸 第X条（剔除已匹配的《…》整体，防双计）
            rest = _BOOK_RE.sub("", content)
            for m in _BARE_RE.finditer(rest):
                found += 1
                ano = f"第{m.group(1)}条"
                if ano in own_articles:
                    resolved += 1
                    targets.append(article_index[(doc_id, ano)])
                else:
                    unresolved.append({
                        "doc_id": doc_id, "article_no": b.article_no,
                        "target": ano, "reason": "本文无此条（可能指代他法/已删条）",
                    })

            b.ref_out = sorted(set(targets))

    return found, resolved, unresolved


def resolution_rate(found: int, resolved: int) -> float:
    return (resolved / found) if found else 1.0


def gate_passed(resolved: int, found: int) -> bool:
    return resolution_rate(found, resolved) >= RESOLUTION_GATE
