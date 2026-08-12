"""试卷（E03）数据访问。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..model.paper import ExamPaper, ExamPaperQuestion


class PaperRepo:
    @staticmethod
    def get_by_id(db: Session, pid: int) -> ExamPaper | None:
        return db.get(ExamPaper, pid)

    @staticmethod
    def get_by_id_for_update(db: Session, pid: int) -> ExamPaper | None:
        """锁定读（当前读）拿试卷行：delete/update 的状态判断需防并发竞态（#17 TOCTOU）。"""
        return db.scalar(select(ExamPaper).where(ExamPaper.id == pid).with_for_update())

    @staticmethod
    def create_paper(db: Session, **kwargs) -> ExamPaper:
        p = ExamPaper(**kwargs)
        db.add(p)
        db.commit()
        db.refresh(p)
        return p

    @staticmethod
    def add_questions(db: Session, paper_id: int, items: list[tuple[int, int, int]]) -> None:
        """批量写试卷-题目关联。items: (question_id, score, seq)，seq 从 1 起。"""
        db.add_all(
            [ExamPaperQuestion(paper_id=paper_id, question_id=qid, score=score, seq=seq) for qid, score, seq in items]
        )
        db.commit()

    @staticmethod
    def create_with_questions(
        db: Session, paper_kwargs: dict, items: list[tuple[int, int, int]]
    ) -> ExamPaper:
        """组卷单事务：试卷行 + 题目关联一次 commit。

        相比 create_paper / add_questions 两步各自 commit，第二步失败会留下
        无题目的孤儿试卷行（question_count=N 却无关联），此处保证原子（#16）。
        """
        p = ExamPaper(**paper_kwargs)
        db.add(p)
        db.flush()  # 取 paper.id，不提交
        db.add_all(
            [ExamPaperQuestion(paper_id=p.id, question_id=qid, score=score, seq=seq)
             for qid, score, seq in items]
        )
        db.commit()
        db.refresh(p)
        return p

    @staticmethod
    def list_questions(db: Session, paper_id: int) -> list[ExamPaperQuestion]:
        return list(
            db.scalars(
                select(ExamPaperQuestion)
                .where(ExamPaperQuestion.paper_id == paper_id)
                .order_by(ExamPaperQuestion.seq)
            )
        )

    @staticmethod
    def delete_questions(db: Session, paper_id: int) -> None:
        db.query(ExamPaperQuestion).filter(ExamPaperQuestion.paper_id == paper_id).delete()
        db.commit()

    @staticmethod
    def list_page(
        db: Session,
        *,
        keyword: str | None = None,
        gen_mode: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ExamPaper], int]:
        conds = []
        if keyword:
            conds.append(ExamPaper.name.like(f"%{keyword}%"))
        if gen_mode:
            conds.append(ExamPaper.gen_mode == gen_mode)
        if status:
            conds.append(ExamPaper.status == status)

        total = db.scalar(select(func.count(ExamPaper.id)).where(*conds)) or 0
        items = list(
            db.scalars(
                select(ExamPaper)
                .where(*conds)
                .order_by(ExamPaper.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total
