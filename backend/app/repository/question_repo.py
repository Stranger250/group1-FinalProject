"""题库（E01）数据访问与列表筛选。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..model.question import Question, QuestionStatus


class QuestionRepo:
    @staticmethod
    def get_by_id(db: Session, qid: int) -> Question | None:
        return db.get(Question, qid)

    @staticmethod
    def list_page(
        db: Session,
        *,
        type_: str | None = None,
        difficulty: str | None = None,
        knowledge_point: str | None = None,
        status: str | None = None,
        source: str | None = None,
        batch_id: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Question], int]:
        conds = []
        if type_:
            conds.append(Question.type == type_)
        if difficulty:
            conds.append(Question.difficulty == difficulty)
        if knowledge_point:
            conds.append(Question.knowledge_point == knowledge_point)
        if status:
            conds.append(Question.status == status)
        if source:
            conds.append(Question.source == source)
        if batch_id:
            conds.append(Question.batch_id == batch_id)
        if keyword:
            conds.append(Question.content.like(f"%{keyword}%"))

        total = db.scalar(select(func.count(Question.id)).where(*conds)) or 0
        items = list(
            db.scalars(
                select(Question)
                .where(*conds)
                .order_by(Question.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    @staticmethod
    def create(db: Session, **kwargs) -> Question:
        q = Question(**kwargs)
        db.add(q)
        db.commit()
        db.refresh(q)
        return q

    @staticmethod
    def create_batch(db: Session, items: list[dict]) -> list[Question]:
        """批量入库（同 batch_id 一批）：单事务 add_all + commit 一次。

        相比逐题 create（各自 commit），保证「要么整批落库、要么整批回滚」——
        避免 AI 出题批次中途某题校验失败留下已提交的半批 PENDING 草稿（#8）。
        """
        qs = [Question(**kwargs) for kwargs in items]
        db.add_all(qs)
        db.commit()
        for q in qs:
            db.refresh(q)
        return qs

    @staticmethod
    def update_many(db: Session, items: list[tuple[Question, dict]]) -> list[Question]:
        """批量更新（单事务）：items=[(question, fields)]，逐题 setattr 后 commit 一次。

        用于整批审核等「要么全部生效、要么全部回滚」的场景（#9）。
        """
        for q, fields in items:
            for k, v in fields.items():
                setattr(q, k, v)
        db.commit()
        for q, _ in items:
            db.refresh(q)
        return [q for q, _ in items]

    @staticmethod
    def update(db: Session, question: Question, **kwargs) -> Question:
        # 上层用 model_dump(exclude_unset=True) 传入，只有客户端显式给出的字段；
        # 值为 None 的字段用于清空可空列（analysis/options/review_note 等），不能跳过。
        for k, v in kwargs.items():
            setattr(question, k, v)
        db.commit()
        db.refresh(question)
        return question

    @staticmethod
    def delete(db: Session, question: Question) -> None:
        db.delete(question)
        db.commit()

    @staticmethod
    def list_by_batch(db: Session, batch_id: str) -> list[Question]:
        """按批次取全部题目，按 id 升序（E02 整批审核）。"""
        return list(
            db.scalars(
                select(Question)
                .where(Question.batch_id == batch_id)
                .order_by(Question.id)
            )
        )

    @staticmethod
    def get_pending_rewrite(db: Session, parent_id: int) -> Question | None:
        """原题待审的修订版（同一原题至多一条，DB 层 uk_rewrite_pending 兜底）。"""
        return db.scalar(
            select(Question).where(
                Question.rewrite_of == parent_id,
                Question.status == QuestionStatus.PENDING,
            )
        )

    @staticmethod
    def has_active_rewrite(db: Session, parent_id: int) -> bool:
        """原题是否存在待审/已通过的修订版。

        存在时禁止直接复核原题通过，避免同一逻辑题重复入卷（原 REJECTED 题与修订版并存）。
        """
        return (
            db.scalar(
                select(Question.id)
                .where(
                    Question.rewrite_of == parent_id,
                    Question.status.in_([QuestionStatus.PENDING, QuestionStatus.APPROVED]),
                )
                .limit(1)
            )
            is not None
        )

    @staticmethod
    def has_approved_rewrite(db: Session, parent_id: int) -> bool:
        """原题是否已有「已通过」的修订版（就地替换语义下禁止再重写，防同一逻辑题重复入卷）。"""
        return (
            db.scalar(
                select(Question.id)
                .where(
                    Question.rewrite_of == parent_id,
                    Question.status == QuestionStatus.APPROVED,
                )
                .limit(1)
            )
            is not None
        )

    @staticmethod
    def batch_stats(db: Session, batch_id: str) -> dict:
        """批次审核统计：一次 SQL 按状态分组计数。

        返回 {"total", "pending", "approved", "rejected"}；
        total 覆盖全部状态（含 DISABLED），供 E02 审核通过率统计。
        """
        rows = db.execute(
            select(Question.status, func.count(Question.id))
            .where(Question.batch_id == batch_id)
            .group_by(Question.status)
        ).all()
        counts = {status: cnt for status, cnt in rows}
        return {
            "total": sum(counts.values()),
            "pending": counts.get(QuestionStatus.PENDING, 0),
            "approved": counts.get(QuestionStatus.APPROVED, 0),
            "rejected": counts.get(QuestionStatus.REJECTED, 0),
        }
