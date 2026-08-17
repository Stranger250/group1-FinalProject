"""管理端用户管理 API（T3，路由前缀 /api/v1/users，仅 ADMIN）。

- 列表 GET /users：分页 + 关键字（用户名/姓名）+ 角色 + 状态筛选；
- 更新 PUT /users/{id}：改角色 / 启用禁用（自我保护：不能操作自身、至少保留一个启用管理员）；
- 重置密码 POST /users/{id}/reset-password：管理员生成临时密码并返回（一次性展示）。

全部 return resp(...)。越权（非 ADMIN）由 require_roles 拦 403。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import require_roles
from ..model.user import RoleId, User
from ..schema.user import UserUpdateIn
from ..service.user_service import AdminUserService
from ..utils.response import resp

router = APIRouter(prefix="/api/v1/users", tags=["用户管理"])

_ADMIN = require_roles(RoleId.ADMIN)


@router.get("", summary="用户列表（ADMIN，分页 + 筛选）")
def list_users(
    keyword: str | None = Query(default=None, description="用户名/姓名关键字"),
    role_id: int | None = Query(default=None, ge=1, le=3, description="角色：1员工/2安全员/3管理员"),
    status_: int | None = Query(default=None, alias="status", ge=0, le=1, description="状态：0禁用/1启用"),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(_ADMIN),
    db: Session = Depends(get_db),
):
    return resp(AdminUserService.list_page(
        db, page=page, page_size=page_size, keyword=keyword, role_id=role_id, status_=status_,
    ))


@router.put("/{uid}", summary="更新用户角色/状态（ADMIN）")
def update_user(
    uid: int,
    payload: UserUpdateIn,
    user: User = Depends(_ADMIN),
    db: Session = Depends(get_db),
):
    return resp(AdminUserService.update(db, user, uid, **payload.model_dump()))


@router.post("/{uid}/reset-password", summary="重置用户密码（ADMIN，重置为默认 123456）")
def reset_password(
    uid: int,
    user: User = Depends(_ADMIN),
    db: Session = Depends(get_db),
):
    return resp(AdminUserService.reset_password(db, uid))
