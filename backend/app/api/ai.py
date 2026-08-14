"""考试工坊 E02 AI 出题接口（AI 生成 + 审核）。

职责（对齐 AI_SOLUTION §6 / DATABASE.md §6.1）：
- 生成：AI 按知识点/题型/数量生成题目，source=ai、status=PENDING 入草稿库，
  一次生成同 batch_id 一批，每次 ≥ GEN_MIN_COUNT（默认 5）题；
- 批次：批次列表（含审核通过率）、批次题目详情、AI 出题统计；
- 审核：单题审核 / 整批（或部分）批量审核，APPROVED 入库 / REJECTED 驳回，
  落 reviewer / review_note / interference_verified。

约定：
- 统一响应 {code, message, data}（app.utils.response.resp）；
- 全部接口仅 安全管理员(SAFETY)/系统管理员(ADMIN) 可访问；
- 生成结果 JSON 经 Pydantic 校验，解析失败自动重试，仍失败抛 LLMError → 502；
- 入库前校验 sources 溯源与 source_law_title / source_article_no 一致。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..ai.doc_extract import REF_DOC_EXTS, extract_text
from ..ai.llm_client import LLMError
from ..core.config import get_settings
from ..core.database import get_db
from ..core.security import require_roles
from ..model.user import RoleId
from ..schema.ai import BatchReviewIn, GenRequest, ReviewIn, RewriteIn
from ..service.gen_service import GenService
from ..service.review_service import ReviewService
from ..utils.response import resp

router = APIRouter(prefix="/api/v1/ai", tags=["AI 出题"])

# 全部 E02 接口仅管理员（安全管理员 / 系统管理员）
_MANAGE = require_roles(RoleId.SAFETY, RoleId.ADMIN)


@router.post("/generate", summary="AI 生成题目（入 PENDING 草稿）")
async def generate(
    payload: GenRequest,
    db: Session = Depends(get_db),
    user=Depends(_MANAGE),
):
    """按知识点/题型/数量调用 LLM 生成题目并写入草稿库。

    - 生成结果 ≥ GEN_MIN_COUNT 题，同 batch_id 一批，status=PENDING；
    - 输出 JSON 用 Pydantic 校验，解析失败自动重试，仍失败抛 LLMError → 502；
    - sources 溯源与 source_law_title/source_article_no 一致后落库；
    - GenService 内部的 HTTPException（参数不合法等）原样透传。
    """
    try:
        data = await GenService.generate(db, payload, operator_id=user.id)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"AI 生成失败：{e}")
    return resp(data)


@router.post("/doc", summary="上传出题参考文档（解析文本，供 AI 限定出题范围）")
async def upload_ref_doc(
    file: UploadFile = File(...),
    _=Depends(_MANAGE),
):
    """上传出题参考文档：解析为纯文本回传（不落盘），供 AI 出题限定范围。

    - 支持格式：txt/md/pdf/docx（REF_DOC_EXTS），非法扩展名 400；
    - 大小上限 settings.max_upload_mb（默认 5MB），超出 413；
    - 文本超 settings.ref_doc_max_chars（默认 5000）截断并标记 truncated=True；
    - 提取结果含 filename/size/chars/truncated/text，text 由前端回传 /generate。
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in REF_DOC_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文档类型（仅支持 {'/'.join(sorted(REF_DOC_EXTS))}）",
        )
    data = await file.read()
    settings = get_settings()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文档过大（上限 5MB）")
    try:
        text = extract_text(file.filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # pdfplumber / python-docx 未装或解析失败
        raise HTTPException(status_code=500, detail=f"文档解析失败：{exc}")
    chars = len(text)
    truncated = chars > settings.ref_doc_max_chars
    if truncated:
        text = text[: settings.ref_doc_max_chars]
    if not text.strip():
        raise HTTPException(status_code=400, detail="无法从文档中提取到文本内容，请更换文档")
    return resp(
        {
            "filename": file.filename,
            "size": len(data),
            "chars": chars,
            "truncated": truncated,
            "text": text,
        }
    )


@router.get("/batches", summary="生成批次列表（含审核通过率）")
def list_batches(db: Session = Depends(get_db), _=Depends(_MANAGE)):
    """生成批次列表，含每批总题数/待审/通过/驳回数量及审核通过率。"""
    return resp(GenService.list_batches(db))


@router.get("/batches/{batch_id}", summary="批次题目详情")
def batch_detail(batch_id: str, db: Session = Depends(get_db), _=Depends(_MANAGE)):
    """某批次下全部题目详情（含题型、审核状态、溯源 sources 等）。"""
    return resp(GenService.list_batch(db, batch_id))


@router.get("/stats", summary="AI 出题统计")
def stats(db: Session = Depends(get_db), _=Depends(_MANAGE)):
    """AI 出题统计：生成批次/题目总数、审核通过率、按题型/难度分布等。"""
    return resp(GenService.stats(db))


@router.post("/questions/{qid}/review", summary="单题审核")
def review_one(
    qid: int,
    payload: ReviewIn,
    db: Session = Depends(get_db),
    user=Depends(_MANAGE),
):
    """单题审核：APPROVED 入库 / REJECTED 驳回，落 reviewer/review_note/interference_verified。"""
    return resp(ReviewService.review_one(db, qid, payload, user.id))


@router.post("/questions/{qid}/rewrite", summary="AI 重写题目（按驳回意见修订）")
async def rewrite_question(
    qid: int,
    payload: RewriteIn,
    db: Session = Depends(get_db),
    user=Depends(_MANAGE),
):
    """AI 重写已驳回的题目：驳回意见 + 修订要求 + 相关条款回喂 LLM，产出修订版入 PENDING。

    - 仅 source=ai 且 status=REJECTED 可重写，原题状态不变（驳回留痕）；
    - 修订版新题 status=PENDING、rewrite_of=原题 id、独立成新批次，可走常规审核。
    """
    try:
        data = await GenService.rewrite(db, qid, payload, user.id)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"AI 重写失败：{e}")
    return resp(data)


@router.post("/batches/{batch_id}/review", summary="整批/部分批量审核")
def review_batch(
    batch_id: str,
    payload: BatchReviewIn,
    db: Session = Depends(get_db),
    user=Depends(_MANAGE),
):
    """整批/部分批量审核（batch_id 以 path 为准），统一 APPROVED 入库或 REJECTED 驳回。"""
    return resp(ReviewService.review_batch(db, batch_id, payload, user.id))
