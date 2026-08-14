"""在线考试（E04/E05）数据访问。

刻意【不 commit】：事务边界由 ExamService 控制，保障「状态流转 + 明细 + 总分」单事务原子写。
（对 E03 paper_repo commit-per-method 的刻意偏离，见 E04/E05 设计评审结论。）
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from ..model.exam import ExamAnswer, ExamRecord, ExamRecordState
from ..model.paper import ExamPaper, PaperStatus


class ExamRepo:
    @staticmethod
    def get_by_id(db: Session, record_id: int) -> ExamRecord | None:
        return db.get(ExamRecord, record_id)

    @staticmethod
    def get_for_update(db: Session, record_id: int) -> ExamRecord | None:
        """锁定记录行（save/switch 用，锁序与 submit 一致，防 AB-BA 死锁）。"""
        return db.scalar(select(ExamRecord).where(ExamRecord.id == record_id).with_for_update())

    @staticmethod
    def get_ongoing(db: Session, paper_id: int, user_id: int) -> ExamRecord | None:
        return db.scalar(
            select(ExamRecord).where(
                ExamRecord.paper_id == paper_id,
                ExamRecord.user_id == user_id,
                ExamRecord.state == ExamRecordState.ONGOING,
            )
        )

    @staticmethod
    def get_ongoing_for_update(db: Session, paper_id: int, user_id: int) -> ExamRecord | None:
        """锁定读（当前读）找进行中记录：并发 start 冲突后能读到已提交的他方记录。"""
        return db.scalar(
            select(ExamRecord)
            .where(
                ExamRecord.paper_id == paper_id,
                ExamRecord.user_id == user_id,
                ExamRecord.state == ExamRecordState.ONGOING,
            )
            .with_for_update()
        )

    @staticmethod
    def create_record(db: Session, **kwargs) -> ExamRecord:
        r = ExamRecord(**kwargs)
        db.add(r)
        db.flush()  # 不 commit，由外层事务/保存点控制
        return r

    @staticmethod
    def list_answers(db: Session, record_id: int) -> list[ExamAnswer]:
        return list(db.scalars(select(ExamAnswer).where(ExamAnswer.record_id == record_id)))

    @staticmethod
    def upsert_answer(
        db: Session,
        record_id: int,
        question_id: int,
        user_answer: str,
        correct_answer: str,
        is_correct: int,
        score: int,
    ) -> None:
        """INSERT..ON DUPLICATE KEY UPDATE：依赖 uk_record_question，幂等 upsert。"""
        stmt = insert(ExamAnswer).values(
            record_id=record_id,
            question_id=question_id,
            user_answer=user_answer,
            correct_answer=correct_answer,
            is_correct=is_correct,
            score=score,
        )
        # correct_answer 一并刷新：题目答案被管理员修改后，判分时覆写为最新规范值（#6）。
        stmt = stmt.on_duplicate_key_update(
            user_answer=user_answer,
            correct_answer=correct_answer,
            is_correct=is_correct,
            score=score,
        )
        db.execute(stmt)

    @staticmethod
    def transition_to_submitted(db: Session, record_id: int, end_time: datetime) -> int:
        """条件 UPDATE：仅 ONGOING → SUBMITTED，返回影响行数（并发双交防重、抢评分权）。"""
        return db.execute(
            update(ExamRecord)
            .where(ExamRecord.id == record_id, ExamRecord.state == ExamRecordState.ONGOING)
            .values(state=ExamRecordState.SUBMITTED, end_time=end_time)
        ).rowcount

    @staticmethod
    def set_cheat_count(db: Session, record_id: int, count: int) -> None:
        db.execute(
            update(ExamRecord).where(ExamRecord.id == record_id).values(cheat_count=count)
        )

    # ---------- 公开选卷 / 考试记录（前端配套接口） ----------

    @staticmethod
    def list_published(
        db: Session, page: int = 1, page_size: int = 20
    ) -> tuple[list[ExamPaper], int]:
        """公开选卷：仅已发布（PUBLISHED）试卷，按发布时间倒序（前端 /exams 选卷页）。"""
        total = db.scalar(
            select(func.count(ExamPaper.id)).where(ExamPaper.status == PaperStatus.PUBLISHED)
        ) or 0
        items = list(
            db.scalars(
                select(ExamPaper)
                .where(ExamPaper.status == PaperStatus.PUBLISHED)
                .order_by(ExamPaper.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    @staticmethod
    def get_ongoing_map(db: Session, user_id: int) -> dict[int, int]:
        """当前用户所有进行中记录 → {paper_id: record_id}（选卷页「继续考试」标识）。"""
        rows = db.execute(
            select(ExamRecord.paper_id, ExamRecord.id).where(
                ExamRecord.user_id == user_id, ExamRecord.state == ExamRecordState.ONGOING
            )
        ).all()
        return {pid: rid for pid, rid in rows}

    @staticmethod
    def list_records_by_user(
        db: Session, user_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[ExamRecord], int]:
        """我的考试记录（全部状态，按开始时间倒序），供前端 /exams/records 分页列表。"""
        total = (
            db.scalar(select(func.count(ExamRecord.id)).where(ExamRecord.user_id == user_id)) or 0
        )
        items = list(
            db.scalars(
                select(ExamRecord)
                .where(ExamRecord.user_id == user_id)
                .order_by(ExamRecord.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total
