"""试卷（E03）ORM 模型（对应 DATABASE.md §6.3/6.4 exam_paper、exam_paper_question 表）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class PaperGenMode:
    MANUAL = "manual"  # 手动组卷：管理员从题库勾选
    AI = "ai"          # AI 智能组卷：按规则自动抽题


class PaperStatus:
    DRAFT = "DRAFT"        # 草稿（默认，可编辑/删除）
    PUBLISHED = "PUBLISHED"  # 已发布（E04 在线考试可选用）
    DISABLED = "DISABLED"  # 已停用


class ExamPaper(Base):
    __tablename__ = "exam_paper"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    total_score: Mapped[int] = mapped_column(Integer)
    pass_score: Mapped[int] = mapped_column(Integer)
    duration: Mapped[int] = mapped_column(Integer)
    question_count: Mapped[int] = mapped_column(Integer)
    difficulty_ratio: Mapped[dict | None] = mapped_column(JSON)  # 组卷配置留痕（AI 组卷写入规则）
    gen_mode: Mapped[str] = mapped_column(String(8), default=PaperGenMode.MANUAL)
    status: Mapped[str] = mapped_column(String(16), default=PaperStatus.DRAFT)
    creator_id: Mapped[int] = mapped_column(BigInteger)
    source_paper_id: Mapped[int | None] = mapped_column(BigInteger, index=True)  # O8 收藏副本来源试卷
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PaperShareStatus:
    ACTIVE = "ACTIVE"      # 分享中（被分享者可查看/作答/收藏）
    REVOKED = "REVOKED"    # 已撤销（不可再查看/作答）


class PaperShare(Base):
    """O8 发布考试记录：试卷 → 指定用户（可多用户）。"""

    __tablename__ = "paper_share"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    target_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=PaperShareStatus.ACTIVE, index=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExamPaperQuestion(Base):
    __tablename__ = "exam_paper_question"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(BigInteger, index=True)
    question_id: Mapped[int] = mapped_column(BigInteger)
    score: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
