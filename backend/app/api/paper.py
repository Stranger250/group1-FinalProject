"""考试工坊 E03 试卷生成接口（手动组卷 / AI 智能组卷）。

职责（对齐 PRD E03 / AI_SOLUTION §6.4）：
- 手动组卷：从题库勾选已审核题目组成试卷；
- AI 智能组卷：按题型数量/知识点/难度分布自动抽题，不足时给出提示；
- 试卷列表（分页/筛选）、详情（题目预览）、更新配置、删除（已发布不可删）。

约定：
- 统一响应 {code, message, data}；
- 全部接口仅 安全管理员(SAFETY)/系统管理员(ADMIN) 可访问；
- 组卷仅取 status=APPROVED 的题目。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_roles
from ..model.user import RoleId
from ..schema.paper import PaperAutoCreate, PaperManualCreate, PaperUpdate
from ..service.paper_service import PaperService
from ..utils.response import resp

router = APIRouter(prefix="/api/v1/papers", tags=["考试工坊 E03 试卷"])

_MANAGE = require_roles(RoleId.SAFETY, RoleId.ADMIN)


@router.post("/manual", summary="手动组卷（勾选题目组成试卷）")
def create_manual(
    payload: PaperManualCreate,
    db: Session = Depends(get_db),
    user=Depends(_MANAGE),
):
    return resp(PaperService.create_manual(db, payload, operator_id=user.id))


@router.post("/auto", summary="AI 智能组卷（按题型数量/难度/知识点自动抽题）")
def create_auto(
    payload: PaperAutoCreate,
    db: Session = Depends(get_db),
    user=Depends(_MANAGE),
):
    return resp(PaperService.create_auto(db, payload, operator_id=user.id))


@router.get("", summary="试卷列表（分页 + 筛选）")
def list_papers(
    gen_mode: str | None = Query(default=None, description="manual/ai"),
    status: str | None = Query(default=None, description="DRAFT/PUBLISHED/DISABLED"),
    keyword: str | None = Query(default=None, description="试卷名称模糊搜索"),
    page: int = Query(default=1, ge=1, le=100000),  # 上限防 MySQL OFFSET 溢出（#13）
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(_MANAGE),
):
    return resp(
        PaperService.list_page(
            db, gen_mode=gen_mode, status=status, keyword=keyword, page=page, page_size=page_size
        )
    )


@router.get("/{pid}", summary="试卷详情（题目预览，含答案）")
def get_paper(pid: int, db: Session = Depends(get_db), _=Depends(_MANAGE)):
    return resp(PaperService.get(db, pid))


@router.put("/{pid}", summary="更新试卷配置（名称/时长/合格线/总分/状态）")
def update_paper(
    pid: int,
    payload: PaperUpdate,
    db: Session = Depends(get_db),
    user=Depends(_MANAGE),
):
    return resp(PaperService.update(db, pid, payload, operator_id=user.id))


@router.delete("/{pid}", summary="删除试卷（已发布不可删）")
def delete_paper(pid: int, db: Session = Depends(get_db), _=Depends(_MANAGE)):
    PaperService.delete(db, pid)
    return resp(message="删除成功")
