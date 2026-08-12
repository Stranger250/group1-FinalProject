"""在线考试（E04/E05）ORM 模型（对应 DATABASE.md §6.5/6.6 exam_record、exam_answer 表）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ExamRecordState:
    ONGOING = "ONGOING"        # 进行中：刷新恢复、防重复开考、双交防护的载体
    SUBMITTED = "SUBMITTED"    # 已交卷（终态）：之后任何 save/submit/switch/resume 幂等返回成绩单


class ExamRecordResultStatus:
    PASS = "PASS"
    FAIL = "FAIL"
    UNGRADED = ""   # 未评分占位（ONGOING 阶段，NOT NULL 约束所需）


class ExamRecord(Base):
    __tablename__ = "exam_record"
    __table_args__ = (
        # 唯一约束 uk_user_paper_ongoing 在 DB 侧基于生成列 ongoing_key（仅 ONGOING 参与唯一），
        # ORM 不映射该生成列，由 DB 自动维护——见 database/schema.sql 中 exam_record 定义。
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(
        String(16), default=ExamRecordResultStatus.UNGRADED, server_default=text("''")
    )
    state: Mapped[str] = mapped_column(
        String(16), default=ExamRecordState.ONGOING, server_default=text("'ONGOING'")
    )
    cheat_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    submit_reason: Mapped[str | None] = mapped_column(String(16))  # manual/timeout/cheat_limit（留痕）
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)  # naive 本地时间，显式写入（DDL 无 server default）
    end_time: Mapped[datetime | None] = mapped_column(DateTime)


class ExamAnswer(Base):
    __tablename__ = "exam_answer"
    __table_args__ = (
        # INSERT..ON DUPLICATE KEY UPDATE 的 DB 锚点：每 (record_id,question_id) 仅一行
        UniqueConstraint("record_id", "question_id", name="uk_record_question"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(BigInteger)
    question_id: Mapped[int] = mapped_column(BigInteger)
    user_answer: Mapped[str] = mapped_column(String(255))  # 规范化后作答（未作答=''）
    correct_answer: Mapped[str] = mapped_column(String(255))
    is_correct: Mapped[int] = mapped_column(mysql.TINYINT, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)
