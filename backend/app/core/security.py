"""密码哈希（bcrypt）与 JWT（python-jose）。

注意：直接用 bcrypt，勿引入 passlib（passlib 1.7.4 读取已删除的 bcrypt.__about__，与已装 bcrypt 5.0 不兼容）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..model.user import User
from .config import get_settings
from .database import get_db

settings = get_settings()

# 用 HTTPBearer 而非 OAuth2PasswordBearer：
# Swagger UI 对 oauth2 password flow 有已知 bug，授权后请求头会带 "Bearer undefined"
# （token 未正确存储），导致 JWT 解码必然失败。HTTPBearer 让用户在 Swagger 里直接粘贴
# /api/v1/auth/login 返回的 access_token，稳定可靠。
oauth2_scheme = HTTPBearer(auto_error=False)

_CRED_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="登录已过期或无效",
    headers={"WWW-Authenticate": "Bearer"},
)

_NO_TOKEN_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="未登录，请在 Authorize 中填入 access_token",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_password(plain: str) -> str:
    """bcrypt 哈希（cost=12）。密码超 72 字节时抛 400 而非 500。"""
    try:
        return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"密码不合法：{e}")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <token> 解析并返回当前用户；缺失/无效/过期抛 401。"""
    if credentials is None:
        raise _NO_TOKEN_EXC
    try:
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise _CRED_EXC
    user = db.get(User, user_id)
    if user is None:
        raise _CRED_EXC
    # 复核账号状态：禁用（status!=1）后既有未过期 JWT 立即失效，而非等 120 分钟过期（#15）
    if user.status != 1:
        raise _CRED_EXC
    return user


def require_roles(*role_ids: int):
    """接口级角色校验：当前用户 role_id 不在允许列表内抛 403。

    用法：Depends(require_roles(RoleId.SAFETY, RoleId.ADMIN))
    """

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role_id not in role_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限访问该接口")
        return user

    return checker
