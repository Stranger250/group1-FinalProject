"""O10 法规文档库服务：列表/详情/上传入库/停用/删除。

数据流：
- 列表/详情：MySQL knowledge_document + knowledge_chunk 聚合（条数=父块数、字数=Σ长度）；
- 上传入库：multipart 文件 → 解析纯文本 → 构造 O4 JSON（单章按段落分条）→
  复用建库管道（clean→parser→ref→MySQL 增量 + Chroma 增量 upsert）；
- 停用：MySQL status=DISABLED + Chroma 删除该文档块（检索即时排除）；
- 启用：MySQL status=SUCCESS + Chroma 按 MySQL chunks 重新嵌入 upsert；
- 删除：MySQL 删行 + Chroma 删块。
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select, text

from ..core.config import get_settings
from ..core.database import SessionLocal
from ..model.chat import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentStatus
from ..rag.embedder import get_embedder
from ..rag.retriever import get_retriever
from ..utils.doc_parse import parse_upload

logger = logging.getLogger("rag.document")

# 类型 → 展示名（O10 六类语料）
DOC_TYPE_LABELS = {
    "law": "法律",
    "regulation": "法规",
    "company": "企业制度",
    "sop": "操作规程",
    "plan": "预案",
    "case": "案例",
}
# 类型 → 行政层级（与 retriever._tier_of 同口径：企业语料=更低级）
TIER_BY_TYPE = {"company": "lower", "sop": "lower", "plan": "lower", "case": "lower"}


def _tier_of(doc_type: str | None, region: str | None) -> str:
    if doc_type in TIER_BY_TYPE:
        return "lower"
    if (region or "") == "四川":
        return "province"
    return "national"


def _doc_out(row, article_count: int, char_count: int) -> dict:
    doc_type = row.doc_type or ""
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "doc_type": doc_type,
        "doc_type_label": DOC_TYPE_LABELS.get(doc_type, doc_type or "未分类"),
        "doc_level": row.doc_level,
        "region": row.region,
        "tier": _tier_of(doc_type, row.region),
        "status": row.status,
        "chunk_count": row.chunk_count,
        "article_count": article_count,
        "char_count": char_count,
        "source_url": row.source_url,
        "create_time": row.create_time.isoformat() if row.create_time else None,
        "update_time": row.update_time.isoformat() if row.update_time else None,
    }


def list_documents(
    *,
    doc_type: str | None = None,
    tier: str | None = None,
    keyword: str | None = None,
    status_: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """文档列表（分页 + 类型/层级/关键字/状态筛选）。"""
    stmt = select(KnowledgeDocument)
    if doc_type:
        stmt = stmt.where(KnowledgeDocument.doc_type == doc_type)
    if status_:
        stmt = stmt.where(KnowledgeDocument.status == status_)
    if keyword:
        stmt = stmt.where(KnowledgeDocument.name.like(f"%{keyword}%"))

    with SessionLocal() as db:
        # 统计条数/字数（父块数 = vector_id 不含 _s；字数 = Σ content 长度）
        agg = (
            select(
                KnowledgeChunk.document_id,
                func.sum(
                    func.if_(func.instr(KnowledgeChunk.vector_id, "_s") == 0, 1, 0)
                ).label("article_count"),
                func.sum(func.char_length(KnowledgeChunk.content)).label("char_count"),
            )
            .group_by(KnowledgeChunk.document_id)
        )
        agg_map = {r.document_id: r for r in db.execute(agg).all()}

        total = db.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()
        rows = db.execute(
            stmt.order_by(KnowledgeDocument.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()

    items = []
    for row in rows:
        a = agg_map.get(row.id)
        items.append(_doc_out(row, a.article_count if a else 0, a.char_count if a else 0))

    # tier 筛选（内存过滤，量级 ≤ 200 篇可接受）
    if tier:
        items = [i for i in items if i["tier"] == tier]
    return {"page": page, "page_size": page_size, "total": total, "items": items}


def get_document(doc_id: int) -> dict:
    """文档详情：元信息 + 正文预览（按章分组展示父块，条号从 vector_id 反解）。"""
    with SessionLocal() as db:
        row = db.get(KnowledgeDocument, doc_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文档不存在")
        chunks = db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == doc_id)
            .order_by(KnowledgeChunk.seq)
        ).scalars().all()

    chapters: list[dict] = []
    by_chapter: dict[str, list[dict]] = {}
    for c in chunks:
        # 子块（vector_id 含 _s）不单独展示，父块即展示单元
        if "_s" in (c.vector_id or ""):
            continue
        ch_name = c.chapter or "正文"
        by_chapter.setdefault(ch_name, []).append({
            "article_no": _article_no_from_vector(c.vector_id),
            "content": c.content,
            "seq": c.seq,
        })
    for ch_name, arts in by_chapter.items():
        chapters.append({"chapter": ch_name, "articles": sorted(arts, key=lambda a: a["seq"])})

    agg = {"article_count": sum(len(x["articles"]) for x in chapters),
           "char_count": sum(len(a["content"]) for x in chapters for a in x["articles"])}
    return {**_doc_out(row, agg["article_count"], agg["char_count"]), "chapters": chapters}


def _article_no_from_vector(vector_id: str) -> str:
    """vector_id 形如 {doc_id}_{article_no}_v{ver} 或 {doc_id}_chapter{n}_v{ver} → 还原条号。"""
    if not vector_id:
        return ""
    parts = vector_id.rsplit("_v", 1)
    body = parts[0]
    # 去掉 doc_id 前缀（第一个下划线前）
    idx = body.find("_")
    if idx >= 0:
        body = body[idx + 1:]
    return body


# ---------- 上传入库 ----------

def _upload_text_to_raw(text: str, *, title: str, doc_type: str, doc_level: int | None,
                        region: str | None, source_url: str | None, filename: str) -> dict:
    """解析后的纯文本 → O4 原始 JSON（单章"正文"，按空行/段落分条）。

    条号规则：段落自动编号「第1段/第2段…」→ parser 的 article_no 取 no 字段。
    """
    paras = [p.strip() for p in text.replace("\r\n", "\n").split("\n") if p.strip()]
    articles = []
    for i, p in enumerate(paras, start=1):
        # 过短的碎片（<12 字）且非句子结尾 → 并入上一条（避免碎块）
        if articles and len(p) < 12 and not p.endswith(("。", "；", "；", "：", "）", "》")):
            articles[-1]["content"] += "\n" + p
        else:
            articles.append({"no": f"第{i}段", "content": p})
    return {
        "title": title,
        "doc_type": doc_type,
        "category": DOC_TYPE_LABELS.get(doc_type, doc_type),
        "doc_level": doc_level or 0,
        "region": region or "",
        "source": "手动上传",
        "source_url": source_url or "",
        "publish_date": "",
        "effective_date": "",
        "status": "有效",
        "chapters": [{"chapter": "正文", "articles": articles}],
    }


def _build_single(raw: dict, fname: str):
    """单文档走建库管道：merge→clean→parse→tag。返回 (doc_id, blocks)。"""
    from ..rag.build.clean import clean_doc
    from ..rag.build.loader import _merge_short_articles
    from ..rag.build.parser import parse_doc, tag_blocks

    merged = _merge_short_articles(raw)
    doc = clean_doc(merged, fname)
    blocks = parse_doc(doc)
    tag_blocks(blocks)
    return doc.doc_id, blocks


def _mysql_insert_doc(db, doc_id: str, blocks, title: str, raw: dict, uploader_id: int) -> int:
    """增量写 MySQL：返回 knowledge_document.id。"""
    doc = blocks[0]
    kdoc = KnowledgeDocument(
        name=title,
        type=raw.get("category") or doc.category,
        doc_type=doc.doc_type,
        doc_level=doc.doc_level,
        region=doc.region,
        source_url=doc.source_url,
        path=f"{title}.json",
        status=KnowledgeDocumentStatus.SUCCESS,
        chunk_count=len(blocks),
        uploader_id=uploader_id,
    )
    db.add(kdoc)
    db.flush()
    db_doc_id = int(kdoc.id)
    for b in blocks:
        db.add(KnowledgeChunk(
            document_id=db_doc_id,
            content=b.content,
            chapter=b.chapter or None,
            page_no=None,
            seq=b.seq,
            vector_id=b.chunk_id,
        ))
    db.commit()
    return db_doc_id


def _chroma_upsert_blocks(blocks, existing_ids: set[str] | None = None) -> int:
    """增量 upsert 块到 Chroma（batch=32），返回实际写入数。

    existing_ids=None 时从 Chroma 自查该 doc 已有 chunk_id（防重复覆盖）。
    """
    from ..rag.build.loader import EMBED_BATCH

    settings = get_settings()
    import chromadb
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    col = client.get_or_create_collection(settings.chroma_collection)
    embedder = get_embedder()

    if existing_ids is None and blocks:
        doc_id = blocks[0].doc_id
        try:
            got = col.get(where={"doc_id": doc_id}, include=[])
            existing_ids = set(got["ids"] or [])
        except Exception:
            existing_ids = set()
    existing_ids = existing_ids or set()

    pending = [b for b in blocks if b.chunk_id not in existing_ids]
    count = 0
    for i in range(0, len(pending), EMBED_BATCH):
        batch = pending[i:i + EMBED_BATCH]
        vecs = embedder.embed_documents([b.content for b in batch])
        col.upsert(
            ids=[b.chunk_id for b in batch],
            documents=[b.content for b in batch],
            embeddings=vecs,
            metadatas=[b.meta_snapshot() for b in batch],
        )
        count += len(batch)
    client.close()
    return count


def _chroma_delete_by_doc(doc_id: str) -> int:
    """从 Chroma 删除某文档全部块（where doc_id），返回删除数。"""
    from ..core.config import get_settings
    import chromadb
    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    col = client.get_or_create_collection(settings.chroma_collection)
    deleted = 0
    try:
        got = col.get(where={"doc_id": doc_id}, include=[])
        if got["ids"]:
            col.delete(ids=got["ids"])
            deleted = len(got["ids"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chroma 删除 doc=%s 失败: %s", doc_id, exc)
    client.close()
    return deleted


def _refresh_retriever() -> None:
    """停用/删除后让常驻检索器重载索引（块集合变化即时生效）。"""
    try:
        get_retriever().reload()
    except Exception as exc:  # noqa: BLE001 —— 重载失败不阻断主流程
        logger.warning("retriever 重载失败: %s", exc)


# ---------- 上传（同步执行，文档级 ≤10MB、块级嵌入，数百块秒级完成） ----------

def upload_document(
    file: UploadFile,
    *,
    title: str,
    doc_type: str,
    doc_level: int | None,
    region: str | None,
    source_url: str | None,
    uploader_id: int,
) -> dict:
    """上传文档 → 解析 → 建库管道 → MySQL+Chroma 增量入库。返回新文档信息。"""
    if doc_type not in DOC_TYPE_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail=f"文档类型不合法：{doc_type}（可选 {'/'.join(DOC_TYPE_LABELS)}）")

    parsed = parse_upload(file, max_chars=None)  # 白名单 + 魔数 + ≤10MB；建库需全文，不截断
    title = (title or "").strip() or parsed["filename"]
    raw = _upload_text_to_raw(
        parsed["text"], title=title, doc_type=doc_type, doc_level=doc_level,
        region=region, source_url=source_url, filename=parsed["filename"],
    )
    fname = f"{title}.json"

    doc_id, blocks = _build_single(raw, fname)
    with SessionLocal() as db:
        # 同名文档已存在 → 400（防重复建库）
        dup = db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.name == title)
        ).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"文档《{title}》已存在（id={dup.id}）")

        db_doc_id = _mysql_insert_doc(db, doc_id, blocks, title, raw, uploader_id)

    try:
        # Chroma 自查该 doc 已有块（同名 doc_id 来自 crawler_output 时跳过），实际写入数
        added = _chroma_upsert_blocks(blocks)
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            db.execute(text("DELETE FROM knowledge_chunk WHERE document_id=:id"), {"id": db_doc_id})
            db.execute(text("DELETE FROM knowledge_document WHERE id=:id"), {"id": db_doc_id})
            db.commit()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"向量入库失败：{exc}")

    _refresh_retriever()
    return {"id": db_doc_id, "doc_id": doc_id, "title": title, "blocks": len(blocks),
            "added_chunks": added, "status": KnowledgeDocumentStatus.SUCCESS}


# ---------- 停用 / 启用 / 删除 ----------

def set_document_status(doc_id: int, status_: str) -> dict:
    """停用（DISABLED）/ 启用（SUCCESS）。

    - 停用：Chroma 删该文档块 → 检索即时排除；
    - 启用：从 MySQL chunks 读回内容重新嵌入 upsert（块级重建）。
    """
    if status_ not in ("DISABLED", "SUCCESS"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="status 仅支持 DISABLED/SUCCESS")

    with SessionLocal() as db:
        row = db.get(KnowledgeDocument, doc_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文档不存在")
        if row.status == status_:
            return {"id": doc_id, "status": row.status, "changed": False}

        if status_ == "DISABLED":
            deleted = _chroma_delete_by_doc(_doc_id_of(row, db))
            row.status = status_
            db.commit()
            _refresh_retriever()
            return {"id": doc_id, "status": row.status, "changed": True, "deleted_chunks": deleted}

        # 启用：重建向量（MySQL chunks 有内容与 vector_id；meta 从首块/文档行组装）
        chunks = db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id)
        ).scalars().all()
        if not chunks:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="文档无分块，无法启用")
        blocks = [_rebuild_block(c, row) for c in chunks]
        added = _chroma_upsert_blocks(blocks, set())
        row.status = status_
        row.chunk_count = len(chunks)
        db.commit()
    _refresh_retriever()
    return {"id": doc_id, "status": status_, "changed": True, "rebuilt_chunks": added}


def delete_document(doc_id: int) -> dict:
    """删除文档（含 MySQL 行 + Chroma 块）。"""
    with SessionLocal() as db:
        row = db.get(KnowledgeDocument, doc_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文档不存在")
        chroma_doc_id = _doc_id_of(row, db)
        db.execute(text("DELETE FROM knowledge_chunk WHERE document_id=:id"), {"id": doc_id})
        db.execute(text("DELETE FROM knowledge_document WHERE id=:id"), {"id": doc_id})
        db.commit()
    deleted = _chroma_delete_by_doc(chroma_doc_id)
    _refresh_retriever()
    return {"id": doc_id, "deleted_chunks": deleted}


def _doc_id_of(row, db) -> str:
    """取 Chroma 侧 doc_id：优先从该文档任意块的 vector_id 反解，否则 md5(title)。"""
    cid = db.execute(
        text("SELECT vector_id FROM knowledge_chunk WHERE document_id=:id LIMIT 1"),
        {"id": row.id},
    ).scalar_one_or_none()
    if cid:
        # vector_id = {doc_id}_{article_no}_v{ver} / {doc_id}_chapter{n}_v{ver} / {doc_id}_s{..}
        return cid.split("_")[0]
    import hashlib
    return f"d{hashlib.md5((row.name or '').encode('utf-8')).hexdigest()[:10]}"


def _rebuild_block(c: KnowledgeChunk, row) -> "Block":
    """从 MySQL chunk 行重建 Block（启用停用文档时用）。

    vector_id 反解 doc_id / article_no / is_parent / parent_id：
      {doc_id}_{article_no}_v{ver}（父块）、{doc_id}_chapter{n}_v{ver}（章头）、{doc_id}_s{n}（子块）
    """
    from ..rag.build.parser import Block

    vid = c.vector_id or ""
    doc_id = vid.split("_")[0]
    is_parent = "_s" not in vid
    parent_id = vid.split("_s")[0] if not is_parent else vid
    body = vid
    if "_s" in vid:
        body = vid.split("_s")[0]
    article_no = ""
    if "_v" in body:
        head = body.rsplit("_v", 1)[0]
        idx = head.find("_")
        if idx >= 0:
            article_no = head[idx + 1:]
    return Block(
        chunk_id=vid,
        doc_id=doc_id,
        title=row.name or "",
        doc_no="",
        category=row.type or "",
        doc_level=row.doc_level or 0,
        region=row.region or "",
        chapter=c.chapter or "",
        article_no=article_no,
        content=c.content,
        is_parent=is_parent,
        parent_id=parent_id,
        seq=c.seq,
        status="有效",
        publish_date="",
        effective_date="",
        version="v1",
        is_latest=True,
        source_url=row.source_url or "",
        doc_type=row.doc_type or "regulation",
        access_level="公开",
    )
