"""落库编排：清洗→解析→引用→打标→MySQL 双写 + Chroma 向量库（M1）。

数据流：
  raw JSON → clean_doc → parse_doc → build_article_index → scan_refs（回填 ref_out）
  → tag_blocks（difficulty）→ Phase A MySQL（docs+chunks 单事务）→
  Phase B 嵌入 + Chroma upsert（batch=32）。

幂等：--force 先删 MySQL 两表 + delete_collection；Chroma 用新持久目录 backend/data/chroma_kb
（绝不指向实训根 PDF 语料 chroma_db）。二次 --force 不翻倍。
"""
from __future__ import annotations

import glob
import json
import logging
import os
from dataclasses import dataclass, field

from sqlalchemy import text

from ..embedder import get_embedder
from .clean import STALE_LAW_FLAGS, CleanedDoc, clean_doc
from .parser import Block, parse_doc, tag_blocks
from .ref import build_article_index, gate_passed, scan_refs

logger = logging.getLogger("rag.build")

EMBED_BATCH = 32


@dataclass
class BuildStats:
    data_dir: str = ""
    files: int = 0
    chapters: int = 0
    articles: int = 0
    full_chars: int = 0
    total_blocks: int = 0
    parent_blocks: int = 0
    child_blocks: int = 0
    ref_found: int = 0
    ref_resolved: int = 0
    ref_unresolved: list = field(default_factory=list)
    stale_flagged: list = field(default_factory=list)
    chroma_count: int = 0
    mysql_docs: int = 0
    mysql_chunks: int = 0
    embedding_time_s: float = 0.0
    db_time_s: float = 0.0

    @property
    def ref_rate(self) -> float:
        return (self.ref_resolved / self.ref_found) if self.ref_found else 1.0


# ---------- 读取与管道 ----------

def load_raw_docs(data_dir: str) -> list[tuple[str, dict]]:
    paths = sorted(glob.glob(os.path.join(data_dir, "*.json")))
    paths = [p for p in paths if not p.endswith("index.json") and not os.path.basename(p).startswith("_")]
    docs: list[tuple[str, dict]] = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            docs.append((os.path.basename(p), json.load(f)))
    return docs


def _merge_short_articles(raw: dict, min_chars: int = 150, max_chars: int = 400) -> dict:
    """合并碎条款（提速优化）：企业语料条款平均仅 85 字，块数爆炸拖慢嵌入。

    规则（仅对 case/plan/company/sop 执行；法规 law/regulation 条号语义保留不合并）：
    - 相邻条款累计长度 < min_chars 或下一条很短（<80 字）且累计不超 max_chars → 合并（\n 连接）；
    - 长条款（>max_chars 或独立语义）保持单条，由 parser 二次分块；
    - article_no 取首条号，内容保留原文本完整。
    """
    doc_type = raw.get("doc_type") or "法规"
    if doc_type in ("law", "regulation", "法规"):
        return raw
    chapters = []
    for ch in raw.get("chapters") or []:
        arts = [a for a in (ch.get("articles") or []) if (a.get("content") or "").strip()]
        merged: list[dict] = []
        buf_no, buf_text = "", ""
        for a in arts:
            no = (a.get("no") or "").strip()
            content = (a.get("content") or "").strip()
            if not buf_text:
                buf_no, buf_text = no, content
            elif len(buf_text) + len(content) <= max_chars and (
                    len(buf_text) < min_chars or len(content) < 80):
                buf_text += "\n" + content
            else:
                merged.append({"no": buf_no, "content": buf_text})
                buf_no, buf_text = no, content
        if buf_text:
            merged.append({"no": buf_no, "content": buf_text})
        chapters.append({"chapter": ch.get("chapter", ""), "articles": merged})
    out = dict(raw)
    out["chapters"] = chapters
    return out


def build_blocks(docs_raw: list[tuple[str, dict]]) -> tuple[list[CleanedDoc], dict[str, list[Block]], BuildStats]:
    """全量清洗+解析，返回 (cleaned_docs, blocks_by_doc, 统计)。未做引用扫描。"""
    cleaned_docs: list[CleanedDoc] = []
    blocks_by_doc: dict[str, list[Block]] = {}
    stats = BuildStats()
    for fname, raw in docs_raw:
        raw = _merge_short_articles(raw)  # 提速：合并企业语料碎条款（法规除外）
        doc = clean_doc(raw, fname)
        blocks = parse_doc(doc)
        cleaned_docs.append(doc)
        blocks_by_doc[doc.doc_id] = blocks
        stats.chapters += len(doc.chapters)
        stats.articles += sum(len(ch["articles"]) for ch in doc.chapters)
        # 全文字数以 full_text 为准（含章标题/条号头，与盘点审计 full_text_chars 一致）
        stats.full_chars += len(raw.get("full_text") or "")
        stats.parent_blocks += sum(1 for b in blocks if b.is_parent)
        stats.child_blocks += sum(1 for b in blocks if not b.is_parent)
        if doc.title in STALE_LAW_FLAGS:
            stats.stale_flagged.append(doc.title)
    stats.files = len(docs_raw)
    stats.total_blocks = stats.parent_blocks + stats.child_blocks
    return cleaned_docs, blocks_by_doc, stats


def scan_and_tag(blocks_by_doc: dict[str, list[Block]]) -> BuildStats:
    """引用扫描（回填 ref_out）+ 打标。返回引用统计。

    O4 真实语料修正：交叉引用扫描仅对法规类文档（law/regulation/法规）执行——
    企业制度/规程/预案/事故报告中的「第X条」多为对法规的引用而非文档间交叉引用，
    全量扫描会把这些计为 unresolved 导致覆盖率闸门（≥90%）误判失败。
    """
    law_blocks = {
        doc_id: blocks for doc_id, blocks in blocks_by_doc.items()
        if blocks[0].doc_type in ("law", "regulation", "法规")
    }
    article_index = build_article_index(law_blocks)
    version_by_doc = {doc_id: blocks[0].version for doc_id, blocks in law_blocks.items()}
    found, resolved, unresolved = scan_refs(law_blocks, article_index, version_by_doc)
    for blocks in blocks_by_doc.values():
        tag_blocks(blocks)
    stats = BuildStats()
    stats.ref_found = found
    stats.ref_resolved = resolved
    stats.ref_unresolved = unresolved
    return stats


# ---------- Phase A：MySQL ----------

def _write_mysql(blocks_by_doc: dict[str, list[Block]], force: bool) -> tuple[int, int, float]:
    """docs + chunks 双写（单事务）。返回 (doc_rows, chunk_rows, 耗时秒)。"""
    import time

    from sqlalchemy.orm import Session

    from ...core.config import get_settings
    from ...core.database import SessionLocal
    from ...model.chat import KnowledgeChunk, KnowledgeDocument

    settings = get_settings()
    started = time.time()

    with SessionLocal() as session:
        admin_id = session.execute(
            text("SELECT id FROM `user` WHERE username = :u"), {"u": settings.admin_username}
        ).scalar()
        if not admin_id:
            raise RuntimeError(f"管理员账号 {settings.admin_username!r} 不存在，无法作为 uploader_id；先跑 init_db.py")

        if force:
            session.execute(text("DELETE FROM knowledge_chunk"))
            session.execute(text("DELETE FROM knowledge_document"))
            session.flush()

        doc_rows = 0
        chunk_rows = 0
        for doc_id, blocks in blocks_by_doc.items():
            doc = blocks[0]
            kdoc = KnowledgeDocument(
                name=doc.title,
                type=doc.category,
                path=doc.title + ".json",  # 源文件与 title 同名（已核实）
                status="SUCCESS",
                chunk_count=len(blocks),
                uploader_id=int(admin_id),
            )
            session.add(kdoc)
            session.flush()  # 拿自增 id
            db_doc_id = int(kdoc.id)
            for b in blocks:
                b.db_doc_id = db_doc_id
                kchunk = KnowledgeChunk(
                    document_id=db_doc_id,
                    content=b.content,
                    chapter=b.chapter or None,
                    page_no=None,
                    seq=b.seq,
                    vector_id=b.chunk_id,
                )
                session.add(kchunk)
                session.flush()  # 逐条 flush 拿自增 id（2700 级规模可接受）
                b.db_chunk_id = int(kchunk.id)
                if b.is_parent:
                    b.parent_db_chunk_id = b.db_chunk_id  # 父块即自身
                chunk_rows += 1
            doc_rows += 1
        # 子块父指针回填：父块 db_chunk_id 已知，二次遍历
        for blocks in blocks_by_doc.values():
            by_chunk = {b.chunk_id: b for b in blocks}
            for b in blocks:
                if not b.is_parent:
                    parent = by_chunk.get(b.parent_id)
                    if parent and parent.db_chunk_id is not None:
                        b.parent_db_chunk_id = parent.db_chunk_id
        session.commit()

    elapsed = time.time() - started
    return doc_rows, chunk_rows, elapsed


# ---------- Phase B：嵌入 + Chroma ----------

def _write_chroma(blocks_by_doc: dict[str, list[Block]], force: bool) -> tuple[int, float]:
    """批量嵌入 + Chroma upsert（batch=32，空间 cosine）。返回 (计数, 耗时秒)。"""
    import time

    import chromadb

    from ...core.config import get_settings

    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    if force:
        try:
            client.delete_collection(settings.chroma_collection)  # 不用 rmtree（Windows 文件锁）
        except Exception:
            pass
    # hnsw:sync_threshold 必须 > 总块数：chromadb 1.5.9 的 WAL→HNSW 同步落盘
    # 在默认 1000 条触发时存在幽灵路径 bug（只写 index_metadata.pickle、不写 .bin，
    # 新进程读报 "Error loading hnsw index"）。调大后中间同步不触发，由 close()
    # 单次全量落盘那条路径（已实测 2544 条 + threshold=100000 通过）。
    collection = client.get_or_create_collection(
        settings.chroma_collection,
        metadata={"hnsw:space": "cosine", "hnsw:sync_threshold": 100000},
    )

    embedder = get_embedder()
    started = time.time()
    count = 0
    batch_ids: list[str] = []
    batch_docs: list[str] = []
    batch_meta: list[dict] = []

    def flush() -> None:
        nonlocal count
        if not batch_ids:
            return
        vecs = embedder.embed_documents(batch_docs)  # 满批嵌入
        collection.upsert(
            ids=batch_ids, documents=batch_docs,
            embeddings=vecs, metadatas=batch_meta,
        )
        count += len(batch_ids)
        batch_ids.clear(); batch_docs.clear(); batch_meta.clear()

    for blocks in blocks_by_doc.values():
        for b in blocks:
            batch_ids.append(b.chunk_id)
            batch_docs.append(b.content)
            batch_meta.append(b.meta_snapshot())
            if len(batch_ids) >= EMBED_BATCH:
                flush()
    if batch_ids:
        flush()

    # 关键：显式 close 触发 compactor 把 WAL 队列落盘（HNSW 二进制）。
    # chromadb 1.5.9 Rust 后端靠进程内后台 compactor 合并 WAL→HNSW segment；
    # 不 close 直接退进程，向量 segment 只处理到 max_seq_id 2048/2544，
    # 新进程读取报 "backfill request to compactor / loading hnsw index"。
    client.close()

    # 落盘自检：起新鲜子进程验证 count+query（同进程读是内存态，掩盖幽灵路径 bug）。
    # chromadb 1.5.x 后台 compactor 在存储写失败时可能只落 index_metadata.pickle
    # 而无 .bin（幽灵路径，PR #5923 类问题）——这里立刻发现，省去整轮断言后才发现。
    import subprocess
    import sys

    _code = (
        "import sys, chromadb\n"
        "client = chromadb.PersistentClient(path=sys.argv[1])\n"
        "col = client.get_or_create_collection(sys.argv[2])\n"
        "n = col.count()\n"
        "res = col.query(query_embeddings=[[1.0]+[0.0]*1023], n_results=2, include=[])\n"
        "client.close()\n"
        "print(n, len(res['ids'][0]))\n"
    )
    p = subprocess.run(
        [sys.executable, "-c", _code, settings.chroma_persist_dir, settings.chroma_collection],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if not (p.returncode == 0 and p.stdout.strip().startswith(str(count))):
        raise RuntimeError(
            "Chroma 落盘校验失败（新鲜进程不可读）：compactor 未把 HNSW 落盘。\n"
            f"  rc={p.returncode} out={p.stdout.strip()!r} err={p.stderr.strip()[:200]!r}\n"
            "  排查：关闭可能并发访问 data/chroma_kb 的进程后重跑 --force。"
        )
    logger.info("Chroma 落盘自检通过：新鲜进程 count=%s", count)

    elapsed = time.time() - started
    return count, elapsed


# ---------- 顶层编排 ----------

def run_build(data_dir: str, force: bool = False, write_mysql: bool = True,
              write_chroma: bool = True) -> tuple[BuildStats, dict[str, list[Block]]]:
    """一键建库。返回 (统计, blocks_by_doc)；调用方负责验收断言。"""
    logger.info("读取数据目录: %s", data_dir)
    docs_raw = load_raw_docs(data_dir)
    logger.info("命中 JSON 文件 %d 部", len(docs_raw))

    cleaned, blocks_by_doc, stats = build_blocks(docs_raw)
    ref_stats = scan_and_tag(blocks_by_doc)
    stats.ref_found = ref_stats.ref_found
    stats.ref_resolved = ref_stats.ref_resolved
    stats.ref_unresolved = ref_stats.ref_unresolved

    # 覆盖率闸门：<90% 直接失败（契约 §1.6）
    if not gate_passed(stats.ref_resolved, stats.ref_found):
        raise RuntimeError(
            f"交叉引用解析覆盖率 {stats.ref_rate:.1%} < 90%，构建中止；"
            f"unresolved={len(stats.ref_unresolved)}"
        )

    if write_mysql:
        stats.mysql_docs, stats.mysql_chunks, stats.db_time_s = _write_mysql(blocks_by_doc, force)
    if write_chroma:
        stats.chroma_count, stats.embedding_time_s = _write_chroma(blocks_by_doc, force)

    return stats, blocks_by_doc
