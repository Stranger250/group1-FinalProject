"""O8 用户端考试工坊 API：我的试卷（组卷/发布考试/撤销/导出 Word）+ 分享给我的（概要/作答/收藏副本）。

- 全部接口任意登录用户可访问（owner/被分享者校验在 service）；
- 发布考试：POST /my-papers/{id}/publish，body {target_user_ids: []}（昵称搜索由用户搜索接口支撑）；
- 被分享试卷作答：直接调 /exams/start（paper 已 PUBLISHED，走既有在线考试链路）；
- 用户搜索用户：GET /users/search（按昵称/用户名模糊，供发布考试下拉选择）。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import get_current_user
from ..model.user import User
from ..schema.paper import PaperManualCreate, PaperUpdate
from ..service.user_paper_service import UserPaperService
from ..utils.response import resp

router = APIRouter(prefix="/api/v1", tags=["考试工坊 O8 用户试卷"])


class PublishIn(BaseModel):
    target_user_ids: list[int] = Field(min_length=1, max_length=100)


# ---------- 我的试卷 ----------

@router.get("/my-papers", summary="我的试卷（含收藏副本，creator 隔离）")
def list_my_papers(
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.list_mine(db, user, page=page, page_size=page_size))


@router.post("/my-papers", summary="手动组卷（从题库选题，仅 APPROVED 题）")
def create_my_paper(
    payload: PaperManualCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.create_manual(db, payload, user))


@router.get("/my-papers/{pid}", summary="我的试卷详情（含题目与答案）")
def get_my_paper(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.get(db, pid, user))


@router.put("/my-papers/{pid}", summary="更新试卷配置（仅草稿）")
def update_my_paper(
    pid: int,
    payload: PaperUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.update(db, pid, payload, user))


@router.delete("/my-papers/{pid}", summary="删除试卷（仅草稿）")
def delete_my_paper(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.delete(db, pid, user))


# ---------- 发布考试（指定用户） ----------

@router.post("/my-papers/{pid}/publish", summary="发布考试：试卷 → 指定用户（可多选，自动收集作答统计）")
def publish_paper(
    pid: int,
    payload: PublishIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.publish(db, pid, payload.target_user_ids, user))


@router.get("/my-papers/{pid}/shares", summary="发布列表（谁可见）")
def list_shares(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.list_shares(db, pid, user))


@router.delete("/my-papers/{pid}/shares/{target_user_id}", summary="撤销对指定用户的发布")
def revoke_share(
    pid: int,
    target_user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.revoke_share(db, pid, target_user_id, user))


@router.get("/my-papers/{pid}/export-word", summary="试卷另存为 Word（?answers=1 含答案版）")
def export_word(
    pid: int,
    answers: int = Query(default=0, ge=0, le=1, description="1=含答案版，0=仅题目版"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = UserPaperService.export_word(db, pid, user, with_answers=answers == 1)
    filename = f"paper_{pid}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- 分享给我的（查看 / 收藏） ----------

@router.get("/shared-papers", summary="分享给我的试卷（ACTIVE，含发布者）")
def list_shared(
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.list_shared_to_me(db, user, page=page, page_size=page_size))


@router.get("/shared-papers/{pid}", summary="被分享试卷概要（答案脱敏，供预览/作答前确认）")
def shared_detail(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.shared_detail(db, pid, user))


@router.post("/shared-papers/{pid}/copy", summary="添加到我的试卷库（收藏副本，source_paper_id 快照）")
def copy_shared(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(UserPaperService.copy_shared(db, pid, user))


# ---------- 用户搜索（发布考试选择目标用户） ----------

@router.get("/users/search", summary="按昵称/用户名搜索用户（供发布考试指定用户下拉选择，排除自己）")
def search_users(
    keyword: str = Query(default="", max_length=64, description="昵称或用户名关键字"),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import or_, select
    from ..model.user import User as _U

    conds = [_U.status == 1, _U.id != user.id]
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        conds.append(or_(_U.name.like(like), _U.username.like(like)))
    rows = list(db.scalars(select(_U).where(*conds).order_by(_U.id.desc()).limit(page_size)))
    return resp({"items": [
        {"id": u.id, "name": u.name, "username": u.username, "role_id": u.role_id} for u in rows
    ]})
