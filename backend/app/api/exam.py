"""考试工坊接口（E01 题库管理先落地；E02-E05 后续 Phase 追加）。

E01 为管理类接口：仅 安全管理员(SAFETY)/系统管理员(ADMIN) 可访问。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_roles
from ..model.user import RoleId
from ..schema.question import (
    QuestionCreate,
    QuestionDifficulty,
    QuestionSource,
    QuestionStatus,
    QuestionType,
    QuestionUpdate,
)
from ..service.question_service import QuestionService
from ..utils.response import resp

router = APIRouter(prefix="/api/v1", tags=["考试工坊"])

# 管理类接口允许的角色
_MANAGE = require_roles(RoleId.SAFETY, RoleId.ADMIN)


@router.get("/questions", summary="题库列表（筛选 + 分页）")
def list_questions(
    type: QuestionType | None = Query(default=None, description="题型 SINGLE/MULTIPLE/JUDGE/FILL"),
    difficulty: QuestionDifficulty | None = Query(default=None, description="难度 EASY/MEDIUM/HARD"),
    knowledge_point: str | None = Query(default=None),
    status: QuestionStatus | None = Query(default=None, description="PENDING/APPROVED/REJECTED/DISABLED"),
    source: QuestionSource | None = Query(default=None, description="manual/ai"),
    batch_id: str | None = Query(default=None),
    keyword: str | None = Query(default=None, description="题干模糊搜索"),
    page: int = Query(default=1, ge=1, le=100000),  # 上限防 MySQL OFFSET 溢出（#13）
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(_MANAGE),
):
    data = QuestionService.list_page(
        db,
        type_=type,
        difficulty=difficulty,
        knowledge_point=knowledge_point,
        status=status,
        source=source,
        batch_id=batch_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return resp(data)


@router.get("/questions/{qid}", summary="题库详情")
def get_question(qid: int, db: Session = Depends(get_db), _=Depends(_MANAGE)):
    return resp(QuestionService.get(db, qid))


@router.post("/questions", summary="手工录入题目（直接 APPROVED 入库）")
def create_question(payload: QuestionCreate, db: Session = Depends(get_db), user=Depends(_MANAGE)):
    return resp(QuestionService.create(db, payload, operator_id=user.id))


@router.put("/questions/{qid}", summary="编辑题目")
def update_question(qid: int, payload: QuestionUpdate, db: Session = Depends(get_db), user=Depends(_MANAGE)):
    return resp(QuestionService.update(db, qid, payload, operator_id=user.id))


@router.delete("/questions/{qid}", summary="删除题目")
def delete_question(qid: int, db: Session = Depends(get_db), _=Depends(_MANAGE)):
    QuestionService.delete(db, qid)
    return resp(message="删除成功")
