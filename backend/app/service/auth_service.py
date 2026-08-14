"""认证业务：注册、登录、签发 JWT、个人中心（资料/改密码/头像）。"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.security import create_access_token, hash_password, verify_password
from ..model.user import RoleId
from ..repository.user_repo import UserRepo


class AuthService:
    @staticmethod
    def register(db: Session, *, username: str, password: str, name: str, phone: str | None) -> dict:
        if UserRepo.get_by_username(db, username):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="用户名已存在")
        try:
            user = UserRepo.create(
                db,
                username=username,
                password=hash_password(password),
                name=name,
                role_id=RoleId.EMPLOYEE,  # 注册只允许普通用户
                phone=phone,
            )
        except IntegrityError:
            # 并发同用户名注册：预检未拦截时撞 uk_username，须转 400 而非裸 500（#10）
            db.rollback()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="用户名已存在")
        return _user_payload(user)

    @staticmethod
    def login(db: Session, *, username: str, password: str) -> dict:
        user = UserRepo.get_by_username(db, username)
        if user is None or not verify_password(password, user.password):
            # 登录失败留痕（用户名可能不存在，user 为 None 时仍记录动作）
            from ..utils.audit import write_audit
            write_audit(db, user, "login_failed", target_type="user",
                        target_id=getattr(user, "id", None), detail=f"username={username}", ip="")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
        if user.status != 1:
            from ..utils.audit import write_audit
            write_audit(db, user, "login_disabled", target_type="user",
                        target_id=user.id, detail="账号已禁用", ip="")
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="账号已禁用")
        token = create_access_token(user.id)
        from ..utils.audit import write_audit
        write_audit(db, user, "login", target_type="user", target_id=user.id, ip="")
        return {"access_token": token, "token_type": "bearer", "user": _user_payload(user)}

    @staticmethod
    def me(user) -> dict:
        """当前用户资料（个人中心初始化 / 会话恢复）。"""
        return _user_payload(user)

    @staticmethod
    def update_profile(db: Session, user, *, name: str, phone: str | None, email: str | None) -> dict:
        """修改个人资料（姓名/手机号/邮箱）。用户名是登录键，不可改。"""
        user.name = name
        user.phone = phone
        user.email = email
        db.commit()
        db.refresh(user)
        return _user_payload(user)

    @staticmethod
    def update_avatar(db: Session, user, avatar_url: str) -> dict:
        """更新头像 URL（图片已由 upload 落盘）。"""
        user.avatar = avatar_url
        db.commit()
        db.refresh(user)
        return _user_payload(user)

    @staticmethod
    def change_password(db: Session, user, *, old_password: str, new_password: str) -> None:
        """修改密码：校验原密码；新旧相同拒绝；成功即令旧 JWT 在新请求中仍有效（状态未变）。"""
        if not verify_password(old_password, user.password):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="原密码不正确")
        if new_password == old_password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="新密码不能与原密码相同")
        user.password = hash_password(new_password)
        db.commit()
        db.refresh(user)


def _user_payload(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role_id": user.role_id,
        "phone": user.phone,
        "email": user.email,
        "avatar": user.avatar,
        "created_time": user.created_time,
        "updated_time": user.updated_time,
    }
