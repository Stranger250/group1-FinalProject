"""试卷生成（E03）业务逻辑：手动组卷 + AI 智能组卷 + 列表/详情/更新/删除。

约定（对齐 PRD E03 / DATABASE.md §6.3-6.4）：
- 组卷仅可选 status=APPROVED 的题目（PENDING/REJECTED/DISABLED 不入卷）；
- 手动组卷：选题 + 分值（全部指定或全部均分，混合填报 400）；
- AI 智能组卷：rules 按「题型 × 难度」抽题（MySQL ORDER BY RAND()），
  题目数不足时给出 warnings 提示，一条规则都没抽到则 400；
- 分值均分：total_score 分摊到每题，余数分摊到前 r 题；
- 删除保护：已发布（PUBLISHED）试卷不可删。
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..model.exam import ExamRecord, ExamRecordState
from ..model.paper import ExamPaper, PaperGenMode, PaperStatus
from ..model.question import Question, QuestionStatus
from ..model.user import User
from ..repository.paper_repo import PaperRepo
from ..schema.paper import PaperAutoCreate, PaperManualCreate


class PaperService:
    @staticmethod
    def _even_split(total: int, n: int) -> list[int]:
        """总分均分到 n 题：base + 余数分摊到前 r 题。"""
        base, rem = divmod(total, n)
        return [base + (1 if i < rem else 0) for i in range(n)]

    @staticmethod
    def _check_score_config(total_score: int, pass_score: int) -> None:
        """跨字段约束：及格线不得高于总分，否则考试永远无法通过（#7）。"""
        if pass_score > total_score:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"及格线 {pass_score} 不能高于总分 {total_score}",
            )

    # ---------- 创建 ----------

    @staticmethod
    def create_manual(db: Session, payload: PaperManualCreate, operator_id: int) -> dict:
        PaperService._check_score_config(payload.total_score, payload.pass_score)
        qids = [pq.question_id for pq in payload.questions]
        if len(set(qids)) != len(qids):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="同一题目不能重复入卷")
        approved = {
            q.id: q
            for q in db.scalars(
                select(Question).where(Question.id.in_(qids), Question.status == QuestionStatus.APPROVED)
            )
        }
        missing = [qid for qid in qids if qid not in approved]
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"以下题目不存在或未审核通过，不可入卷：{missing}",
            )

        # 分值策略：全指定→用指定值；全不指定→均分；混合→400（避免歧义）
        scores = [pq.score for pq in payload.questions]
        if any(s is None for s in scores):
            if any(s is not None for s in scores):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="题目分值需统一：全部指定或全部均分")
            scores = PaperService._even_split(payload.total_score, len(payload.questions))
        elif sum(scores) != payload.total_score:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"题目分值之和 {sum(scores)} 与总分 {payload.total_score} 不一致",
            )

        # 单事务组卷：试卷行 + 题目关联一次落库（#16），避免两步 commit 产生无题孤儿卷
        paper = PaperRepo.create_with_questions(
            db,
            paper_kwargs={
                "name": payload.name,
                "total_score": payload.total_score,
                "pass_score": payload.pass_score,
                "duration": payload.duration,
                "question_count": len(qids),
                "difficulty_ratio": None,
                "gen_mode": PaperGenMode.MANUAL,
                "status": PaperStatus.DRAFT,
                "creator_id": operator_id,
            },
            items=[(qid, s, i) for i, (qid, s) in enumerate(zip(qids, scores), start=1)],
        )
        return PaperService._detail(db, paper)

    @staticmethod
    def create_auto(db: Session, payload: PaperAutoCreate, operator_id: int) -> dict:
        PaperService._check_score_config(payload.total_score, payload.pass_score)
        used: set[int] = set()
        picked: list[Question] = []
        warnings: list[str] = []
        kps = payload.knowledge_points

        for rule in payload.rules:
            conds = [Question.status == QuestionStatus.APPROVED, Question.type == rule.type]
            if rule.difficulty:
                conds.append(Question.difficulty == rule.difficulty)
            if kps:
                conds.append(Question.knowledge_point.in_(kps))
            if used:
                conds.append(Question.id.notin_(list(used)))
            cands = db.scalars(
                select(Question).where(*conds).order_by(func.rand()).limit(rule.count)
            ).all()
            picked.extend(cands)
            used.update(q.id for q in cands)
            if len(cands) < rule.count:
                label = f"{rule.type}({rule.difficulty or '全部难度'})"
                warnings.append(f"{label}: 需求 {rule.count} 题，实际可用 {len(cands)} 题")

        if not picked:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="无可用题目（无已审核题目或条件过严），请调整抽题规则",
            )

        # 单事务组卷（#16），避免两步 commit 产生无题孤儿卷
        scores = PaperService._even_split(payload.total_score, len(picked))
        paper = PaperRepo.create_with_questions(
            db,
            paper_kwargs={
                "name": payload.name,
                "total_score": payload.total_score,
                "pass_score": payload.pass_score,
                "duration": payload.duration,
                "question_count": len(picked),
                "difficulty_ratio": payload.model_dump(exclude_unset=True),  # 组卷配置留痕
                "gen_mode": PaperGenMode.AI,
                "status": PaperStatus.DRAFT,
                "creator_id": operator_id,
            },
            items=[(q.id, scores[i - 1], i) for i, q in enumerate(picked, start=1)],
        )
        data = PaperService._detail(db, paper)
        if warnings:
            data["warnings"] = warnings  # PRD E03 验收：智能组卷不足时给出提示
        return data

    # ---------- 查询 ----------

    @staticmethod
    def get(db: Session, pid: int) -> dict:
        paper = PaperRepo.get_by_id(db, pid)
        if paper is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="试卷不存在")
        return PaperService._detail(db, paper)

    @staticmethod
    def list_page(db: Session, **filters) -> dict:
        items, total = PaperRepo.list_page(db, **filters)
        creators = {
            u.id: u.name
            for u in db.scalars(
                select(User).where(User.id.in_([p.creator_id for p in items] or [0]))
            )
        }
        return {
            "page": filters.get("page", 1),
            "page_size": filters.get("page_size", 20),
            "total": total,
            "items": [
                {
                    "id": p.id,
                    "name": p.name,
                    "total_score": p.total_score,
                    "pass_score": p.pass_score,
                    "duration": p.duration,
                    "question_count": p.question_count,
                    "gen_mode": p.gen_mode,
                    "status": p.status,
                    "creator_id": p.creator_id,
                    "creator_name": creators.get(p.creator_id),
                    "create_time": p.create_time.isoformat() if p.create_time else None,
                }
                for p in items
            ],
        }

    @staticmethod
    def _detail(db: Session, paper: ExamPaper) -> dict:
        links = PaperRepo.list_questions(db, paper.id)
        qs = {
            q.id: q
            for q in db.scalars(
                select(Question).where(Question.id.in_([l.question_id for l in links] or [0]))
            )
        }
        creator = db.get(User, paper.creator_id)
        return {
            "id": paper.id,
            "name": paper.name,
            "total_score": paper.total_score,
            "pass_score": paper.pass_score,
            "duration": paper.duration,
            "question_count": paper.question_count,
            "difficulty_ratio": paper.difficulty_ratio,
            "gen_mode": paper.gen_mode,
            "status": paper.status,
            "creator_id": paper.creator_id,
            "creator_name": creator.name if creator else None,
            "create_time": paper.create_time.isoformat() if paper.create_time else None,
            "questions": [
                {
                    "seq": link.seq,
                    "score": link.score,
                    "question": _question_dict(qs[link.question_id]) if link.question_id in qs else None,
                }
                for link in links
            ],
        }

    # ---------- 更新 / 删除 ----------

    @staticmethod
    def update(db: Session, pid: int, payload, operator_id: int) -> dict:
        # 锁定读（FOR UPDATE）：状态判断与后续写入在同一事务内，防并发竞态（#17）
        paper = PaperRepo.get_by_id_for_update(db, pid)
        if paper is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="试卷不存在")
        fields = payload.model_dump(exclude_unset=True)
        if not fields:
            return PaperService._detail(db, paper)

        # 发布后锁死考核口径（#5）：总分/及格线不可改（判定漂移）；时长在有进行中考试时不可改（倒计时漂移）
        if paper.status == PaperStatus.PUBLISHED:
            if "total_score" in fields or "pass_score" in fields:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="已发布试卷不可修改总分/及格线，请先取消发布",
                )
            if "duration" in fields:
                has_ongoing = (
                    db.scalar(
                        select(ExamRecord.id)
                        .where(
                            ExamRecord.paper_id == pid,
                            ExamRecord.state == ExamRecordState.ONGOING,
                        )
                        .limit(1)
                    )
                    is not None
                )
                if has_ongoing:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail="已有进行中考试，不可修改时长",
                    )

        # 跨字段约束（#7）：改后及格线仍不得高于总分（草稿期）
        new_total = fields.get("total_score", paper.total_score)
        new_pass = fields.get("pass_score", paper.pass_score)
        PaperService._check_score_config(new_total, new_pass)

        for k, v in fields.items():
            setattr(paper, k, v)
        db.commit()
        db.refresh(paper)
        return PaperService._detail(db, paper)

    @staticmethod
    def delete(db: Session, pid: int) -> None:
        # 锁定读：判断状态与删除在同一事务，防「并发发布+删除」绕过已发布保护（#17）
        paper = PaperRepo.get_by_id_for_update(db, pid)
        if paper is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="试卷不存在")
        if paper.status == PaperStatus.PUBLISHED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="已发布试卷不可删除，请先取消发布")
        # 引用检查（#1）：有考试记录（含已交卷历史）的试卷不可删，否则成绩单/进行中记录悬空 500
        has_records = (
            db.scalar(select(ExamRecord.id).where(ExamRecord.paper_id == pid).limit(1)) is not None
        )
        if has_records:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="试卷存在考试记录，不可删除",
            )
        PaperRepo.delete_questions(db, paper.id)
        db.delete(paper)
        db.commit()


def _question_dict(q: Question) -> dict:
    """试卷题目预览字段（含答案，供管理员预览/组卷确认；E04 考生侧另行脱敏）。"""
    return {
        "id": q.id,
        "type": q.type,
        "content": q.content,
        "options": q.options,
        "answer": q.answer,
        "analysis": q.analysis,
        "knowledge_point": q.knowledge_point,
        "difficulty": q.difficulty,
        "source_law_title": q.source_law_title,
        "source_article_no": q.source_article_no,
    }
