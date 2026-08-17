"""认证接口（B01/B02 + 个人中心）：注册、登录、当前用户、资料修改/改密码/头像上传。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.database import get_db
from ..core.security import get_current_user
from ..model.user import User
from ..schema.auth import ChangePasswordIn, ForgotPasswordIn, ProfileUpdateIn, RegisterIn
from ..service.auth_service import AuthService
from ..service.user_service import AdminUserService
from ..utils.response import resp
from ..utils.upload import save_image_upload

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@router.post("/forgot-password", summary="忘记密码：请求重置为默认密码 123456（公开）")
def forgot_password(payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    """登录页「忘记密码」入口：将账号密码重置为默认 123456 并留痕审计。

    实训口径：账号不存在/已禁用统一 404 同文案（防账号枚举）。
    """
    return resp(AdminUserService.request_reset(db, payload.username.strip()))


@router.post("/register", summary="注册（普通用户）")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    data = AuthService.register(db, **payload.model_dump())
    return resp(data)


@router.post("/login", summary="登录（OAuth2 密码模式，签发 JWT）")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    data = AuthService.login(db, username=form.username, password=form.password)
    return resp(data)


@router.get("/me", summary="当前登录用户信息（个人中心初始化）")
def me(user: User = Depends(get_current_user)):
    return resp(AuthService.me(user))


@router.put("/profile", summary="修改个人资料（姓名/手机号/邮箱）")
def update_profile(
    payload: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(AuthService.update_profile(db, user, **payload.model_dump()))


@router.put("/password", summary="修改密码（校验原密码）")
def change_password(
    payload: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthService.change_password(db, user, **payload.model_dump())
    return resp(message="密码已修改")


@router.post("/avatar", summary="上传头像（jpg/png/jpeg ≤5MB）")
def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存头像图片，更新 user.avatar 为 /uploads/... URL，返回更新后的用户资料。"""
    rel = save_image_upload(file, get_settings())
    return resp(AuthService.update_avatar(db, user, f"/uploads/{rel}"))
