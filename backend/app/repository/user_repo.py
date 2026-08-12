"""用户数据访问。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..model.user import User


class UserRepo:
    @staticmethod
    def get_by_username(db: Session, username: str) -> User | None:
        return db.scalar(select(User).where(User.username == username))

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> User | None:
        return db.get(User, user_id)

    @staticmethod
    def create(db: Session, *, username: str, password: str, name: str, role_id: int, phone: str | None = None) -> User:
        user = User(
            username=username,
            password=password,
            name=name,
            role_id=role_id,
            phone=phone,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
