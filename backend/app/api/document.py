"""O10 法规文档库接口。

- GET    /documents            文档列表（分页 + 类型/层级/关键字/状态筛选）
- GET    /documents/{id}       文档详情（元信息 + 正文预览分章展示）
- POST   /documents            管理端上传文档（txt/md/pdf/docx → 建库管道增量入库）
- PUT    /documents/{id}/status 停用（DISABLED）/ 启用（SUCCESS）——检索即时生效
- DELETE /documents/{id}       删除文档（含分块，需确认）

权限：浏览任意登录用户；上传/停用/删除 require_roles(SAFETY, ADMIN)。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from ..core.database import get_db
from ..core.security import get_current_user, require_roles
from ..model.user import RoleId
from ..service.document_service import (
    delete_document,
    list_documents,
    get_document,
    set_document_status,
    upload_document,
)
from ..utils.response import resp

router = APIRouter(prefix="/api/v1/documents", tags=["法规文档库"])

_MANAGE = require_roles(RoleId.SAFETY, RoleId.ADMIN)


@router.get("", summary="O10 文档列表（分页 + 筛选）")
def list_docs(
    doc_type: str | None = Query(default=None, description="law/regulation/company/sop/plan/case"),
    tier: str | None = Query(default=None, description="national/province/lower"),
    keyword: str | None = Query(default=None, description="文档名模糊搜索"),
    status: str | None = Query(default=None, description="PENDING/SUCCESS/FAILED/DISABLED"),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    _=Depends(get_current_user),
):
    return resp(list_documents(
        doc_type=doc_type, tier=tier, keyword=keyword, status_=status,
        page=page, page_size=page_size,
    ))


@router.get("/{doc_id}", summary="O10 文档详情（元信息 + 正文预览）")
def doc_detail(doc_id: int, _=Depends(get_current_user)):
    return resp(get_document(doc_id))


@router.post("", summary="O10 上传文档入库（SAFETY/ADMIN）")
def upload_doc(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, description="文档标题（缺省用文件名）"),
    doc_type: str = Form(..., description="law/regulation/company/sop/plan/case"),
    doc_level: int | None = Form(default=None, description="行政层级 1/2/3/4"),
    region: str | None = Form(default=None, description="区域（如 四川/国家）"),
    source_url: str | None = Form(default=None, description="来源链接"),
    db: Session = Depends(get_db),
    user=Depends(_MANAGE),
):
    return resp(upload_document(
        file, title=title, doc_type=doc_type, doc_level=doc_level,
        region=region, source_url=source_url, uploader_id=user.id,
    ))


@router.put("/{doc_id}/status", summary="O10 停用/启用文档（SAFETY/ADMIN）")
def change_status(
    doc_id: int,
    payload: dict,
    user=Depends(_MANAGE),
):
    status_ = str((payload or {}).get("status") or "").strip().upper()
    return resp(set_document_status(doc_id, status_))


@router.delete("/{doc_id}", summary="O10 删除文档（含分块，SAFETY/ADMIN）")
def remove_doc(doc_id: int, user=Depends(_MANAGE)):
    return resp(delete_document(doc_id))
