"""认证业务：注册、登录、签发 JWT。"""
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
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
        if user.status != 1:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="账号已禁用")
        token = create_access_token(user.id)
        return {"access_token": token, "token_type": "bearer", "user": _user_payload(user)}


def _user_payload(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role_id": user.role_id,
        "phone": user.phone,
    }
