"""认证相关 Pydantic 模型。"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_password_bytes(v: str) -> str:
    # bcrypt 上限 72 字节；64 个汉字=192 字节会超，需按字节校验
    if len(v.encode("utf-8")) > 72:
        raise ValueError("密码过长（utf-8 编码后不能超过 72 字节）")
    return v


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, examples=["zhangsan"])
    password: str = Field(min_length=6, max_length=64, examples=["123456"])
    name: str = Field(min_length=1, max_length=64, examples=["张三"])
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("password")
    @classmethod
    def _password_max_bytes(cls, v: str) -> str:
        return _validate_password_bytes(v)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    role_id: int
    phone: str | None = None
    email: str | None = None
    avatar: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdateIn(BaseModel):
    """个人中心资料修改（T2）：姓名必填，手机号/邮箱选填；用户名登录键不可改。"""

    name: str = Field(min_length=1, max_length=64, examples=["张三"])
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=120)

    @field_validator("phone")
    @classmethod
    def _phone_blank(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not v.isdigit():
            raise ValueError("手机号只能包含数字")
        return v

    @field_validator("email")
    @classmethod
    def _email_format(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("邮箱格式不正确")
        return v


class ChangePasswordIn(BaseModel):
    """修改密码（T2）：需校验原密码，新密码 6-64 位（utf-8 ≤72 字节）。"""

    old_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=6, max_length=64)

    @field_validator("new_password")
    @classmethod
    def _new_password_bytes(cls, v: str) -> str:
        return _validate_password_bytes(v)
