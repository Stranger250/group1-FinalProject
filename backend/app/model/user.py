"""用户与角色 ORM 模型（对应 DATABASE.md §3 role/user 表）。

注意：`user` 是 MySQL 保留字，表名用 quoted_name 强制反引号。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func, quoted_name, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class RoleId:
    """角色 ID（DATABASE.md §8.1 初始化数据）。"""

    EMPLOYEE = 1
    SAFETY = 2
    ADMIN = 3


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(String(255))
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class User(Base):
    __tablename__ = quoted_name("user", quote=True)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(64))
    role_id: Mapped[int] = mapped_column(BigInteger)
    phone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[int] = mapped_column(mysql.TINYINT, default=1, server_default=text("1"), nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
