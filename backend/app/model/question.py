"""题库 ORM 模型（对应 DATABASE.md §6.2 question 表，对齐 PRD §7 全部字段）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, JSON, String, Text, func, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class QuestionType:
    SINGLE = "SINGLE"      # 单选
    MULTIPLE = "MULTIPLE"  # 多选
    JUDGE = "JUDGE"        # 判断
    FILL = "FILL"          # 填空
    SUBJECTIVE = "SUBJECTIVE"  # 解答题（要点包含判分，参考答案分号分隔要点）


class QuestionDifficulty:
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class QuestionSource:
    MANUAL = "manual"  # 人工录入
    AI = "ai"          # AI 生成


class QuestionStatus:
    PENDING = "PENDING"    # 待审核（AI 草稿，未入正式题库）
    APPROVED = "APPROVED"  # 已通过（审核通过，入库可用）
    REJECTED = "REJECTED"  # 已驳回
    DISABLED = "DISABLED"  # 已停用（不入卷）


class Question(Base):
    __tablename__ = "question"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str | None] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSON)
    # 解答题参考答案可达数百字，从 VARCHAR(64) 扩为 TEXT（schema.sql 与 init_db 迁移同步）
    answer: Mapped[str] = mapped_column(Text)
    analysis: Mapped[str | None] = mapped_column(Text)
    knowledge_point: Mapped[str] = mapped_column(String(128), index=True)
    difficulty: Mapped[str] = mapped_column(String(16), index=True)
    source: Mapped[str] = mapped_column(
        String(16), default=QuestionSource.MANUAL, server_default=text("'manual'")
    )
    sources: Mapped[list | None] = mapped_column(JSON)
    source_law_title: Mapped[str | None] = mapped_column(String(255))
    source_article_no: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(16), default=QuestionStatus.PENDING, server_default=text("'PENDING'"), index=True
    )
    reviewer: Mapped[int | None] = mapped_column(BigInteger)
    review_note: Mapped[str | None] = mapped_column(String(255))
    interference_verified: Mapped[int] = mapped_column(mysql.TINYINT, default=0, server_default=text("0"), nullable=False)
    rewrite_of: Mapped[int | None] = mapped_column(BigInteger, index=True)  # 非空=修订自某题 id（E02 重写链）
    rewrite_feedback: Mapped[str | None] = mapped_column(String(255))  # 重写请求的修订要求原文
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
