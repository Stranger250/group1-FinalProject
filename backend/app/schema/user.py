"""管理端用户管理 Pydantic 模型（T3，/api/v1/users）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class UserUpdateIn(BaseModel):
    """管理员更新用户：role_id/status 至少提供一个（name/phone 属个人中心范围，管理端不覆盖）。"""

    role_id: int | None = Field(default=None, ge=1, le=3, description="角色：1员工/2安全员/3管理员")
    status: int | None = Field(default=None, ge=0, le=1, description="状态：0禁用/1启用")
