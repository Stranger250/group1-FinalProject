"""认证相关 Pydantic 模型。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, examples=["zhangsan"])
    password: str = Field(min_length=6, max_length=64, examples=["123456"])
    name: str = Field(min_length=1, max_length=64, examples=["张三"])
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("password")
    @classmethod
    def _password_max_bytes(cls, v: str) -> str:
        # bcrypt 上限 72 字节；64 个汉字=192 字节会超，需按字节校验
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码过长（utf-8 编码后不能超过 72 字节）")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    role_id: int
    phone: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
