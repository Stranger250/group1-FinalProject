"""认证接口（B01/B02）：注册、登录、当前用户。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import get_current_user
from ..model.user import User
from ..schema.auth import RegisterIn
from ..service.auth_service import AuthService
from ..utils.response import resp

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@router.post("/register", summary="注册（普通用户）")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    data = AuthService.register(db, **payload.model_dump())
    return resp(data)


@router.post("/login", summary="登录（OAuth2 密码模式，签发 JWT）")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    data = AuthService.login(db, username=form.username, password=form.password)
    return resp(data)


@router.get("/me", summary="当前登录用户信息")
def me(user: User = Depends(get_current_user)):
    return resp(
        {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "role_id": user.role_id,
            "phone": user.phone,
        }
    )
