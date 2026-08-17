"""管理端用户管理业务（T3）：列表/搜索/筛选、改角色、启禁用、重置密码。"""
from __future__ import annotations

from fastapi import HTTPException, status as http_status
from sqlalchemy.orm import Session

from ..core.security import hash_password
from ..model.user import RoleId, User
from ..repository.user_repo import UserRepo

# 重置密码默认值（实训约定：忘记密码/管理员重置统一为 123456，用户登录后自行修改）
DEFAULT_RESET_PASSWORD = "123456"


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
        """重置密码：统一重置为默认密码 123456（实训约定，返回给管理员展示）。"""
        target = UserRepo.get_by_id(db, user_id)
        if target is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="用户不存在")
        new_password = DEFAULT_RESET_PASSWORD
        UserRepo.set_password(db, target, hash_password(new_password))
        from ..utils.audit import write_audit
        write_audit(db, target, "password_reset", target_type="user", target_id=user_id,
                    detail="管理员重置密码（默认 123456）")
        return {"username": target.username, "new_password": new_password}

    @staticmethod
    def request_reset(db: Session, username: str) -> dict:
        """忘记密码请求重置（登录页公开接口）：将密码重置为默认 123456 并留痕。

        实训口径：校验用户名存在即重置（避免提示「用户不存在」泄露账号枚举，
        统一返回固定文案）；审计记录 action=password_reset_request。
        """
        user = UserRepo.get_by_username(db, username)
        if user is None:
            # 账号不存在也走同口径提示（防枚举），不落库
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="账号不存在或已被禁用，请联系管理员")
        if user.status != 1:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, detail="账号不存在或已被禁用，请联系管理员")
        new_password = DEFAULT_RESET_PASSWORD
        UserRepo.set_password(db, user, hash_password(new_password))
        from ..utils.audit import write_audit
        write_audit(db, user, "password_reset_request", target_type="user", target_id=user.id,
                    detail="忘记密码请求重置（默认 123456）")
        return {"username": user.username, "new_password": new_password}


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
