"""在线考试（E04）+ 自动阅卷（E05）业务逻辑。

核心设计（对齐 E04/E05 设计工作流评审结论）：
- 生命周期：exam_record.state = ONGOING（进行中）/ SUBMITTED（已交卷终态）；交卷后任何
  save/submit/switch/resume 一律幂等返回既有成绩单（200），不重评不覆盖；
- 并发防护：submit 首条语句 = 条件 UPDATE（WHERE state='ONGOING'）原子抢评分权，
  rows=0 → 幂等返回（并发双交只评一次）；save/switch 先 SELECT..FOR UPDATE 锁记录行，
  锁序与 submit 一致（先记录后明细）→ 无 AB-BA 死锁；
- 自动交卷：交互时懒校验（save/submit/switch/resume/start 复用）——now>=deadline（超时）
  或服务端 cheat_count>3（第 4 次切屏）即交卷，reason 优先级 timeout > cheat_limit > manual；
- 阅卷：_grade_all 遍历整卷 exam_paper_question 关联题目（join question.answer），合并
  请求答案与已存答案逐题判分写 exam_answer；未作答也落占位行（user_answer=''）；
- 脱敏：考生侧题目仅 seq/id/type/content/options/score，交卷前任何接口不含答案与解析。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..model.exam import ExamRecord, ExamRecordResultStatus, ExamRecordState
from ..model.paper import ExamPaper, ExamPaperQuestion, PaperStatus
from ..model.question import Question
from ..model.user import RoleId, User
from ..repository import exam_repo
from ..schema.exam import ExamAnswersIn, ExamStartIn, ExamSwitchIn
from ..service.grading_service import canonicalize, grade

CHEAT_LIMIT = 3  # 切屏超过 3 次（第 4 次）触发自动交卷


def _now() -> datetime:
    """统一 naive 本地时间（与 MySQL DATETIME 同口径），禁混用带时区对象。"""
    return datetime.now()


class ExamService:
    # ---------- 开始 / 恢复 ----------

    @staticmethod
    def start(db: Session, payload: ExamStartIn, user: User) -> dict:
        paper = db.get(ExamPaper, payload.paper_id)
        if paper is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="试卷不存在")

        # 复用已有进行中记录（防孤儿记录 + 刷新恢复）：
        # 已有 ONGOING 记录时放行继续考试——即便试卷被管理员中途停用/下架，也不打断进行中的考试（#12）
        record = exam_repo.ExamRepo.get_ongoing(db, paper.id, user.id)
        if record is not None:
            if ExamService._expired(record, paper):
                return ExamService._finalize(db, record.id, user, reason_arg="timeout")
            return ExamService._exam_sheet(db, record, paper)

        # 无进行中记录 → 新开考才要求试卷已发布
        if paper.status != PaperStatus.PUBLISHED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="试卷未发布，不可开考")
        try:
            with db.begin_nested():
                record = exam_repo.ExamRepo.create_record(
                    db,
                    paper_id=paper.id,
                    user_id=user.id,
                    score=0,
                    status=ExamRecordResultStatus.UNGRADED,
                    state=ExamRecordState.ONGOING,
                    cheat_count=0,
                )
        except IntegrityError:
            # 唯一键冲突：锁当前读复用他方已提交记录
            record = exam_repo.ExamRepo.get_ongoing_for_update(db, paper.id, user.id)
            if record is None:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="考试开始冲突，请重试")
        db.commit()

        # 新建分支带超时懒校验：已过期直接自动交卷
        if ExamService._expired(record, paper):
            return ExamService._finalize(db, record.id, user, reason_arg="timeout")
        return ExamService._exam_sheet(db, record, paper)

    @staticmethod
    def resume(db: Session, record_id: int, user: User) -> dict:
        record = ExamService._get_record(db, record_id, user)
        if record.state == ExamRecordState.SUBMITTED:
            return ExamService._result_sheet(db, record)  # 已交卷 → 直接成绩单
        paper = ExamService._require_paper(db, record.paper_id, "继续考试")
        if ExamService._expired(record, paper):
            return ExamService._finalize(db, record.id, user, reason_arg="timeout")
        return ExamService._exam_sheet(db, record, paper)

    # ---------- 保存 / 切屏 / 交卷 ----------

    @staticmethod
    def save(db: Session, record_id: int, user: User, payload: ExamAnswersIn) -> dict:
        record = exam_repo.ExamRepo.get_for_update(db, record_id)
        ExamService._ensure_owner(record, user)
        if record.state == ExamRecordState.SUBMITTED:
            return ExamService._result_sheet(db, record)  # 幂等返回既有成绩单
        paper = ExamService._require_paper(db, record.paper_id, "保存答案")
        # 先落盘本批答案（防丢数据），再做超时/切屏预检
        ExamService._save_answers(db, record_id, paper, payload.answers)
        if ExamService._expired(record, paper):
            return ExamService._finalize(db, record.id, user, reason_arg="timeout")
        if record.cheat_count > CHEAT_LIMIT:
            return ExamService._finalize(db, record.id, user, reason_arg="cheat_limit")
        db.commit()
        return ExamService._exam_sheet(db, record, paper)

    @staticmethod
    def switch(db: Session, record_id: int, user: User, payload: ExamSwitchIn) -> dict:
        record = exam_repo.ExamRepo.get_for_update(db, record_id)
        ExamService._ensure_owner(record, user)
        if record.state == ExamRecordState.SUBMITTED:
            return ExamService._result_sheet(db, record)
        paper = ExamService._require_paper(db, record.paper_id, "上报切屏")
        if ExamService._expired(record, paper):
            return ExamService._finalize(db, record.id, user, reason_arg="timeout")
        merged = max(record.cheat_count, payload.cheat_count)  # 服务端权威，max 合并（防前端重置）
        exam_repo.ExamRepo.set_cheat_count(db, record_id, merged)
        record.cheat_count = merged
        if merged > CHEAT_LIMIT:
            return ExamService._finalize(db, record.id, user, reason_arg="cheat_limit")
        db.commit()
        return {
            "record_id": record.id,
            "cheat_count": merged,
            "remaining_seconds": ExamService._remaining(record, paper),
            "triggered": False,
            "threshold": CHEAT_LIMIT,
        }

    @staticmethod
    def submit(db: Session, record_id: int, user: User, payload: ExamAnswersIn) -> dict:
        # 归属预检（只读）；评分权由 _finalize 条件 UPDATE 原子获取
        ExamService._get_record(db, record_id, user)
        return ExamService._finalize(db, record_id, user, reason_arg="manual", body_answers=payload.answers)

    # ---------- 公开选卷 / 考试记录（前端配套接口） ----------

    @staticmethod
    def list_published_papers(
        db: Session, user: User, page: int = 1, page_size: int = 20
    ) -> dict:
        """公开选卷列表（前端 /exams 选卷页，P0 阻塞项）。

        仅返回 PUBLISHED 试卷，且【脱敏】——不含任何题目与答案；
        每条附带当前用户是否有进行中记录（ongoing_record_id），供「继续考试/开始考试」分流。
        """
        items, total = exam_repo.ExamRepo.list_published(db, page=page, page_size=page_size)
        ongoing = exam_repo.ExamRepo.get_ongoing_map(db, user.id)
        return {
            "page": page,
            "page_size": page_size,
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
                    "create_time": p.create_time.isoformat() if p.create_time else None,
                    "ongoing_record_id": ongoing.get(p.id),
                }
                for p in items
            ],
        }

    @staticmethod
    def list_my_records(db: Session, user: User, page: int = 1, page_size: int = 20) -> dict:
        """我的考试记录分页（前端 /exams/records 页，评审 C3 数据源）。"""
        records, total = exam_repo.ExamRepo.list_records_by_user(
            db, user.id, page=page, page_size=page_size
        )
        papers = db.scalars(
            select(ExamPaper).where(ExamPaper.id.in_([r.paper_id for r in records] or [0]))
        ).all()
        paper_map = {p.id: p for p in papers}
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [
                {
                    "record_id": r.id,
                    "paper_id": r.paper_id,
                    "paper_name": paper_map[r.paper_id].name if r.paper_id in paper_map else "（试卷已删除）",
                    "state": r.state,
                    "status": r.status,
                    "score": r.score,
                    "pass_score": paper_map[r.paper_id].pass_score if r.paper_id in paper_map else None,
                    "passed": r.status == ExamRecordResultStatus.PASS,
                    "reason": r.submit_reason,
                    "cheat_count": r.cheat_count,
                    "start_time": r.start_time.isoformat() if r.start_time else None,
                    "submitted_at": r.end_time.isoformat() if r.end_time else None,
                }
                for r in records
            ],
        }

    # ---------- 成绩单 ----------

    @staticmethod
    def result(db: Session, record_id: int, user: User) -> dict:
        record = exam_repo.ExamRepo.get_by_id(db, record_id)
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="考试记录不存在")
        # 普通用户访问他人记录与「不存在」统一 404（#14 掩码）；SAFETY/ADMIN 放行
        if record.user_id != user.id and user.role_id not in (RoleId.SAFETY, RoleId.ADMIN):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="考试记录不存在")
        if record.state != ExamRecordState.SUBMITTED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="考试尚未交卷，无法查看成绩单")
        return ExamService._result_sheet(db, record)

    # ---------- 内部：阅卷核心 ----------

    @staticmethod
    def _finalize(
        db: Session,
        record_id: int,
        user: User,
        reason_arg: str = "manual",
        body_answers: list | None = None,
    ) -> dict:
        """交卷 + 自动阅卷：条件 UPDATE 原子抢评分权，赢者单事务完成全部分值落库。

        rows==0 分支（已被并发交卷）幂等返回既有成绩单，不写入。
        """
        # 1) 条件 UPDATE（首条语句）：仅 ONGOING → SUBMITTED，兼获记录行 X 锁，防并发双交
        rows = exam_repo.ExamRepo.transition_to_submitted(db, record_id, _now())
        if rows == 0:
            db.rollback()  # 无先前写入，安全；丢弃本事务
            record = exam_repo.ExamRepo.get_by_id(db, record_id)
            return ExamService._result_sheet(db, record)
        # 2) 赢者：重读记录（Core UPDATE 已改库内行，ORM 对象失效后取新值）
        db.expire_all()
        record = exam_repo.ExamRepo.get_by_id(db, record_id)
        paper = ExamService._require_paper(db, record.paper_id, "交卷")
        # 3) 写入请求体答案（submit 路径；save 路径已在此前落盘）
        if body_answers:
            ExamService._save_answers(db, record_id, paper, body_answers)
        # 4) 权威 reason：timeout > cheat_limit > manual（复查服务端切屏计数）
        reason = ExamService._reason(record, paper, reason_arg)
        # 5) 整卷判分 + 落明细 + 写总分/结果/原因（随事务提交）
        ExamService._grade_all(db, record, paper, reason)
        db.commit()
        return ExamService._result_sheet(db, record)

    @staticmethod
    def _grade_all(db: Session, record: ExamRecord, paper: ExamPaper, reason: str) -> None:
        links = db.scalars(
            select(ExamPaperQuestion).where(ExamPaperQuestion.paper_id == paper.id)
        ).all()
        qs = (
            {
                q.id: q
                for q in db.scalars(
                    select(Question).where(Question.id.in_([l.question_id for l in links]))
                )
            }
            if links
            else {}
        )
        saved = {a.question_id: a for a in exam_repo.ExamRepo.list_answers(db, record.id)}
        total = 0
        for link in links:
            q = qs.get(link.question_id)
            if q is None:
                continue  # 题目已被删除等异常，跳过（不落明细）
            user_raw = saved[link.question_id].user_answer if link.question_id in saved else ""
            is_correct, score = grade(q.type, user_raw, q.answer, link.score)
            # correct_answer 存规范化快照（与 user_answer 同口径），供成绩单展示/审计（#6）
            exam_repo.ExamRepo.upsert_answer(
                db,
                record.id,
                link.question_id,
                user_raw,
                canonicalize(q.type, q.answer),
                is_correct,
                score,
            )
            total += score
        # 直接改 ORM 对象（已持有记录行 X 锁），随事务一起提交
        record.score = total
        record.status = "PASS" if total >= paper.pass_score else "FAIL"
        record.submit_reason = reason

    @staticmethod
    def _save_answers(db: Session, record_id: int, paper: ExamPaper, items: list) -> None:
        links = db.scalars(
            select(ExamPaperQuestion).where(ExamPaperQuestion.paper_id == paper.id)
        ).all()
        qs = (
            {
                q.id: q
                for q in db.scalars(
                    select(Question).where(Question.id.in_([l.question_id for l in links]))
                )
            }
            if links
            else {}
        )
        for item in items:
            if item.question_id not in qs:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"题目 {item.question_id} 不属于本试卷")
            q = qs[item.question_id]
            # 存规范化作答；is_correct/score 先占位（NOT NULL），交卷时由阅卷覆写权威值。
            # correct_answer 同步存规范化快照，避免与判分口径漂移（#6）。
            exam_repo.ExamRepo.upsert_answer(
                db,
                record_id,
                item.question_id,
                canonicalize(q.type, item.user_answer),
                canonicalize(q.type, q.answer),
                0,
                0,
            )

    @staticmethod
    def _exam_sheet(db: Session, record: ExamRecord, paper: ExamPaper) -> dict:
        """进行中试卷视图：脱敏题目 + 已存答案 + 倒计时（不含答案/解析）。"""
        if paper is None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="试卷已被删除，考试无法继续")
        links = db.scalars(
            select(ExamPaperQuestion)
            .where(ExamPaperQuestion.paper_id == paper.id)
            .order_by(ExamPaperQuestion.seq)
        ).all()
        qs = (
            {
                q.id: q
                for q in db.scalars(
                    select(Question).where(Question.id.in_([l.question_id for l in links]))
                )
            }
            if links
            else {}
        )
        saved = {a.question_id: a.user_answer for a in exam_repo.ExamRepo.list_answers(db, record.id)}
        now = _now()
        deadline = record.start_time + timedelta(minutes=paper.duration)
        return {
            "record_id": record.id,
            "paper_id": paper.id,
            "paper_name": paper.name,
            "state": record.state,
            "total_score": paper.total_score,
            "pass_score": paper.pass_score,
            "duration": paper.duration,
            "start_time": record.start_time.isoformat() if record.start_time else None,
            "deadline": deadline.isoformat(),
            "remaining_seconds": max(0, int((deadline - now).total_seconds())),
            "server_time": now.isoformat(),
            "cheat_count": record.cheat_count,
            "questions": [
                {
                    "seq": link.seq,
                    "id": link.question_id,
                    "type": qs[link.question_id].type,
                    "content": qs[link.question_id].content,
                    "options": qs[link.question_id].options,
                    "score": link.score,
                }
                for link in links
                if link.question_id in qs
            ],
            "answers": [{"question_id": qid, "user_answer": ans} for qid, ans in saved.items()],
        }

    @staticmethod
    def _result_sheet(db: Session, record: ExamRecord) -> dict:
        """成绩单：总分/是否合格/每题作答/正确答案/解析（交卷后唯一暴露答案与解析处）。"""
        paper = ExamService._require_paper(db, record.paper_id, "查看成绩单")
        links = db.scalars(
            select(ExamPaperQuestion)
            .where(ExamPaperQuestion.paper_id == paper.id)
            .order_by(ExamPaperQuestion.seq)
        ).all()
        qs = (
            {
                q.id: q
                for q in db.scalars(
                    select(Question).where(Question.id.in_([l.question_id for l in links]))
                )
            }
            if links
            else {}
        )
        ans = {a.question_id: a for a in exam_repo.ExamRepo.list_answers(db, record.id)}
        return {
            "record_id": record.id,
            "paper_id": paper.id,
            "paper_name": paper.name,
            "state": record.state,
            "status": record.status,
            "reason": record.submit_reason,
            "total_score": paper.total_score,
            "score": record.score,
            "pass_score": paper.pass_score,
            "passed": record.score >= paper.pass_score,
            "submitted_at": record.end_time.isoformat() if record.end_time else None,
            "start_time": record.start_time.isoformat() if record.start_time else None,
            "duration": paper.duration,
            "cheat_count": record.cheat_count,
            "questions": [
                {
                    "seq": link.seq,
                    "question_id": link.question_id,
                    "type": qs[link.question_id].type,
                    "content": qs[link.question_id].content,
                    "options": qs[link.question_id].options,
                    "user_answer": ans[link.question_id].user_answer if link.question_id in ans else "",
                    # 展示判分时快照（exam_answer.correct_answer），而非可变 question.answer——
                    # 管理员考后改题不会让成绩单出现「判对但标准答案已变」的矛盾（#4）
                    "correct_answer": (
                        ans[link.question_id].correct_answer if link.question_id in ans
                        else qs[link.question_id].answer
                    ),
                    "is_correct": ans[link.question_id].is_correct if link.question_id in ans else 0,
                    "score": ans[link.question_id].score if link.question_id in ans else 0,
                    "analysis": qs[link.question_id].analysis,
                }
                for link in links
                if link.question_id in qs
            ],
        }

    # ---------- 内部：辅助 ----------

    @staticmethod
    def _require_paper(db: Session, paper_id: int, action: str) -> ExamPaper:
        """取试卷，删除/缺失时抛 409 而非 AttributeError 500（#1）。"""
        paper = db.get(ExamPaper, paper_id)
        if paper is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail=f"试卷已被删除，无法{action}"
            )
        return paper

    @staticmethod
    def _get_record(db: Session, record_id: int, user: User) -> ExamRecord:
        """归属校验（只读路径）：不存在 / 非本人 统一 404（#14 掩码，防记录 ID 枚举）。"""
        record = exam_repo.ExamRepo.get_by_id(db, record_id)
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="考试记录不存在")
        if record.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="考试记录不存在")
        return record

    @staticmethod
    def _ensure_owner(record: ExamRecord | None, user: User) -> None:
        """归属校验（写路径：调用方已持有行锁后的记录对象）。统一 404 掩码（#14）。"""
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="考试记录不存在")
        if record.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="考试记录不存在")

    @staticmethod
    def _expired(record: ExamRecord, paper: ExamPaper) -> bool:
        return _now() >= record.start_time + timedelta(minutes=paper.duration)

    @staticmethod
    def _remaining(record: ExamRecord, paper: ExamPaper) -> int:
        deadline = record.start_time + timedelta(minutes=paper.duration)
        return max(0, int((deadline - _now()).total_seconds()))

    @staticmethod
    def _reason(record: ExamRecord, paper: ExamPaper, fallback: str) -> str:
        """交卷原因：timeout > cheat_limit > manual（复查服务端切屏计数，防前端漏报）。"""
        if ExamService._expired(record, paper):
            return "timeout"
        if record.cheat_count > CHEAT_LIMIT:
            return "cheat_limit"
        return fallback
