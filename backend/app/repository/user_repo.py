"""用户数据访问。"""
from __future__ import annotations

from sqlalchemy import func, or_, select
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

    @staticmethod
    def list_page(db: Session, *, page: int, page_size: int,
                  keyword: str | None = None, role_id: int | None = None,
                  status_: int | None = None) -> tuple[int, list[User]]:
        """管理端用户列表（T3）：关键字匹配用户名/姓名 + 角色/状态筛选 + 分页，按创建时间倒序。"""
        stmt = select(User)
        conds = []
        if keyword:
            like = f"%{keyword}%"
            conds.append(or_(User.username.like(like), User.name.like(like)))
        if role_id is not None:
            conds.append(User.role_id == role_id)
        if status_ is not None:
            conds.append(User.status == status_)
        if conds:
            stmt = stmt.where(*conds)
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.scalars(
            stmt.order_by(User.created_time.desc(), User.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        return total or 0, list(rows)

    @staticmethod
    def count_active_by_role(db: Session, role_id: int) -> int:
        """指定角色下启用的用户数（防禁用最后一个管理员）。"""
        return db.scalar(
            select(func.count()).select_from(User).where(User.role_id == role_id, User.status == 1)
        ) or 0

    @staticmethod
    def update_fields(db: Session, user: User, **fields) -> User:
        """按字段名更新（仅更新非 None 字段），commit + refresh。"""
        for k, v in fields.items():
            if v is not None:
                setattr(user, k, v)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def set_password(db: Session, user: User, hashed: str) -> None:
        user.password = hashed
        db.commit()
        db.refresh(user)
