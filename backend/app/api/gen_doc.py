"""O12 Word/PPT 文档生成接口。

- POST /gen-doc/preview   生成大纲预览（DeepSeek 降级路径）
- POST /gen-doc/download  按确认的大纲渲染 .docx / .pptx 并下载

权限：任意登录用户。生成动作留审计（doc_generate）；内容过敏感词检查。
"""
from __future__ import annotations

import io
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import get_current_user
from ..rag.sensitive import contains_sensitive
from ..service.gen_doc_service import (
    DOC_TYPES,
    _MAX_PAGES,
    _MAX_TOPIC,
    generate_outline,
    render_document,
)
from ..utils.audit import write_audit
from ..utils.response import resp

logger = logging.getLogger("rag.gendoc")
router = APIRouter(prefix="/api/v1/gen-doc", tags=["O12 文档生成"])

_SAFE_FILE = re.compile(r"[\\/:*?\"<>|\s]+")


class PreviewIn(BaseModel):
    doc_type: str = Field(pattern="^(word|ppt)$")
    topic: str = Field(min_length=2, max_length=_MAX_TOPIC)
    style: str = Field(default="正式", max_length=64)


class DownloadIn(BaseModel):
    doc_type: str = Field(pattern="^(word|ppt)$")
    topic: str = Field(min_length=2, max_length=_MAX_TOPIC)
    outline: dict  # 预览确认后回传的大纲（服务端再校验结构，防篡改/防敏感词绕过）


@router.post("/preview", summary="O12 生成大纲预览")
async def preview(payload: PreviewIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    hits = contains_sensitive(payload.topic)
    if hits:
        raise HTTPException(status_code=400, detail=f"内容包含敏感词：{'、'.join(hits)}")
    outline = await generate_outline(payload.doc_type, payload.topic, payload.style)
    # 敏感词检查大纲全文（生成内容过敏感词检查，PRD O12 §5）
    dump = str(outline)
    hits = contains_sensitive(dump)
    if hits:
        raise HTTPException(status_code=400, detail=f"大纲包含敏感词：{'、'.join(hits)}")
    # 审计：预览动作（download 时再记一次完整生成）
    try:
        write_audit(db, user, "doc_generate", target_type="gen_doc", target_id=0,
                    detail=f"doc_type={payload.doc_type} topic={payload.topic[:60]} action=preview")
    except Exception:  # noqa: BLE001
        logger.warning("doc_generate 审计写入失败（preview）")
    return resp({"outline": outline})


@router.post("/download", summary="O12 按大纲渲染并下载（.docx/.pptx）")
async def download(payload: DownloadIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    outline = payload.outline
    # 结构校验（防篡改）：word 需 sections 数组；ppt 需 slides 数组且 ≥8 页
    if payload.doc_type == "word":
        if not isinstance(outline.get("sections"), list):
            raise HTTPException(status_code=422, detail="大纲缺少 sections 数组")
    else:
        slides = outline.get("slides")
        if not isinstance(slides, list) or len(slides) < 8:
            raise HTTPException(status_code=422, detail=f"PPT 大纲页数不足（需 ≥8，收到 {len(slides) if isinstance(slides, list) else 0}）")
        if len(slides) > _MAX_PAGES:
            raise HTTPException(status_code=422, detail=f"PPT 大纲页数超限（≤{_MAX_PAGES}）")
    dump = str(outline)
    hits = contains_sensitive(dump)
    if hits:
        raise HTTPException(status_code=400, detail=f"大纲包含敏感词：{'、'.join(hits)}")

    try:
        data = render_document(payload.doc_type, outline)
    except Exception as exc:  # noqa: BLE001
        logger.exception("文档渲染失败")
        raise HTTPException(status_code=500, detail=f"文档渲染失败：{exc}")

    # 审计：完整生成记录
    title = str(outline.get("title") or payload.topic)[:60]
    try:
        write_audit(db, user, "doc_generate", target_type="gen_doc", target_id=0,
                    detail=f"doc_type={payload.doc_type} title={title} bytes={len(data)} action=download")
    except Exception:  # noqa: BLE001
        logger.warning("doc_generate 审计写入失败（download）")

    ext = "docx" if payload.doc_type == "word" else "pptx"
    safe_title = _SAFE_FILE.sub("_", title) or "文档"
    fname = f"{safe_title}.{ext}"
    # 中文文件名：RFC 5987 filename*（latin-1 无法直接编码中文）
    from urllib.parse import quote
    ascii_fallback = _SAFE_FILE.sub("_", fname) or f"output.{ext}"
    content_disposition = (
        f"attachment; filename=\"{quote(ascii_fallback)}\"; "
        f"filename*=UTF-8''{quote(fname)}"
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if payload.doc_type == "word"
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": content_disposition},
    )
