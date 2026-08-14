"""管理端用户管理业务（T3）：列表/搜索/筛选、改角色、启禁用、重置密码。"""
from __future__ import annotations

import secrets

from fastapi import HTTPException, status as http_status
from sqlalchemy.orm import Session

from ..core.security import hash_password
from ..model.user import RoleId, User
from ..repository.user_repo import UserRepo


class AdminUserService:
    @staticmethod
    def list_page(db: Session, *, page: int, page_size: int,
                  keyword: str | None, role_id: int | None, status_: int | None) -> dict:
        total, rows = UserRepo.list_page(
            db, page=page, page_size=page_size,
            keyword=keyword, role_id=role_id, status_=status_,
        )
        return {"items": [_item(u) for u in rows], "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def update(db: Session, operator: User, user_id: int, *, role_id: int | None, status: int | None) -> dict:
        """改角色 / 启用禁用。自我保护：管理员不能操作自身（禁自身/降级会锁死）；至少保留一个启用管理员。

        参数名 status 与 UserUpdateIn.status、user.status 列一致（repo 按字段名 setattr）。
        """
        target = UserRepo.get_by_id(db, user_id)
        if target is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="用户不存在")
        if target.id == operator.id:
            if (role_id is not None and role_id != RoleId.ADMIN) or status == 0:
                raise HTTPException(http_status.HTTP_400_BAD_REQUEST, detail="不能禁用或降级当前登录的管理员账号")
        if status == 0 and target.role_id == RoleId.ADMIN and UserRepo.count_active_by_role(db, RoleId.ADMIN) <= 1:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, detail="系统至少需保留一个启用的管理员")
        # 被禁用账号的 JWT 会被 get_current_user 的 status 复核拦截，立即失效（security.py #15）
        UserRepo.update_fields(db, target, role_id=role_id, status=status)
        from ..utils.audit import write_audit
        write_audit(db, operator, "user_update", target_type="user", target_id=user_id,
                    detail=f"role_id={role_id} status={status}")
        return _item(target)

    @staticmethod
    def reset_password(db: Session, user_id: int) -> dict:
        """重置密码：生成一次性临时密码（返回给管理员展示，仅此一次）。"""
        target = UserRepo.get_by_id(db, user_id)
        if target is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="用户不存在")
        new_password = secrets.token_urlsafe(10)
        UserRepo.set_password(db, target, hash_password(new_password))
        from ..utils.audit import write_audit
        write_audit(db, target, "password_reset", target_type="user", target_id=user_id,
                    detail="管理员重置密码（临时密码一次性返回）")
        return {"username": target.username, "new_password": new_password}


def _item(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role_id": user.role_id,
        "phone": user.phone,
        "email": user.email,
        "avatar": user.avatar,
        "status": user.status,
        "created_time": user.created_time,
        "updated_time": user.updated_time,
    }
