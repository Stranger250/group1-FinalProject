"""O8 用户端考试工坊业务：我的试卷（组卷/编辑/删除/发布考试/撤销/导出 Word）、收藏副本、分享给我的。

复用 PaperService.create_manual / PaperRepo 的组卷与详情能力；新增：
- 发布考试：paper 置 PUBLISHED + paper_share 记录（指定用户，可多选、可撤销）；
- 收藏副本：复制 exam_paper + exam_paper_question（source_paper_id 记录来源，题目快照）；
- 被分享试卷：仅 ACTIVE 分享可见；概要脱敏（不含答案）；可直接作答（/exams/start，paper 已 PUBLISHED）；
- Word 导出：python-docx 渲染（仅题目版/含答案版两模式）。
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..model.paper import ExamPaper, PaperShare, PaperShareStatus, PaperStatus
from ..model.question import Question
from ..model.user import User
from ..repository.paper_repo import PaperRepo
from ..schema.paper import PaperManualCreate
from ..service.paper_service import PaperService


class UserPaperService:
    # ---------- 我的试卷 ----------

    @staticmethod
    def list_mine(db: Session, user: User, page: int = 1, page_size: int = 20) -> dict:
        """我的试卷：creator_id=me（含收藏副本 source_paper_id 标记），按创建时间倒序。"""
        total = db.scalar(select(func.count(ExamPaper.id)).where(ExamPaper.creator_id == user.id)) or 0
        rows = list(db.scalars(
            select(ExamPaper).where(ExamPaper.creator_id == user.id)
            .order_by(ExamPaper.id.desc()).offset((page - 1) * page_size).limit(page_size)
        ))
        return {
            "page": page, "page_size": page_size, "total": int(total or 0),
            "items": [UserPaperService._paper_brief(p) for p in rows],
        }

    @staticmethod
    def _paper_brief(p: ExamPaper) -> dict:
        return {
            "id": p.id,
            "name": p.name,
            "total_score": p.total_score,
            "pass_score": p.pass_score,
            "duration": p.duration,
            "question_count": p.question_count,
            "gen_mode": p.gen_mode,
            "status": p.status,
            "source_paper_id": p.source_paper_id,
            "is_copy": p.source_paper_id is not None,
            "create_time": p.create_time.isoformat() if p.create_time else None,
        }

    @staticmethod
    def _get_owned(db: Session, pid: int, user: User) -> ExamPaper:
        p = PaperRepo.get_by_id(db, pid)
        if p is None or p.creator_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="试卷不存在")
        return p

    @staticmethod
    def create_manual(db: Session, payload: PaperManualCreate, user: User) -> dict:
        """用户手动组卷（复用 PaperService：仅 APPROVED 题可入卷）。"""
        detail = PaperService.create_manual(db, payload, operator_id=user.id)
        detail["is_copy"] = False
        return detail

    @staticmethod
    def get(db: Session, pid: int, user: User) -> dict:
        p = UserPaperService._get_owned(db, pid, user)
        return PaperService.get(db, pid)

    @staticmethod
    def update(db: Session, pid: int, payload, user: User) -> dict:
        p = UserPaperService._get_owned(db, pid, user)
        if p.status != PaperStatus.DRAFT:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="仅草稿状态的试卷可编辑")
        return PaperService.update(db, pid, payload, operator_id=user.id)

    @staticmethod
    def delete(db: Session, pid: int, user: User) -> dict:
        p = UserPaperService._get_owned(db, pid, user)
        if p.status != PaperStatus.DRAFT:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="仅草稿状态的试卷可删除")
        PaperService.delete(db, pid)
        return {"message": "删除成功"}

    # ---------- 发布考试（指定用户） ----------

    @staticmethod
    def publish(db: Session, pid: int, target_user_ids: list[int], user: User) -> dict:
        """发布考试：试卷 → 指定用户（昵称搜索/下拉选择，可多选）。

        校验：仅本人试卷；目标用户存在且启用；至少一个目标；幂等（同卷同人重复发布更新为 ACTIVE）。
        """
        p = UserPaperService._get_owned(db, pid, user)
        ids = sorted({i for i in target_user_ids if i and i != user.id})
        if not ids:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="请至少选择一名被分享用户（不含自己）")
        from ..model.user import User as _U
        rows = db.scalars(select(_U).where(_U.id.in_(ids), _U.status == 1)).all()
        valid = {u.id for u in rows}
        missing = [i for i in ids if i not in valid]
        if missing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"以下用户不存在或已停用：{missing}")

        p.status = PaperStatus.PUBLISHED
        for uid in ids:
            share = db.scalar(select(PaperShare).where(
                PaperShare.paper_id == pid, PaperShare.target_user_id == uid))
            if share is None:
                db.add(PaperShare(paper_id=pid, target_user_id=uid, status=PaperShareStatus.ACTIVE))
            else:
                share.status = PaperShareStatus.ACTIVE
        db.commit()
        from ..utils.audit import write_audit
        write_audit(db, user, "paper_publish", target_type="paper", target_id=pid,
                    detail=f"targets={ids}")
        return {"message": f"已发布给 {len(ids)} 名用户", "status": p.status, "targets": ids}

    @staticmethod
    def list_shares(db: Session, pid: int, user: User) -> dict:
        p = UserPaperService._get_owned(db, pid, user)
        rows = list(db.scalars(select(PaperShare).where(PaperShare.paper_id == pid)
                               .order_by(PaperShare.create_time.desc())))
        names = UserPaperService._names(db, {r.target_user_id for r in rows})
        return {"items": [
            {"target_user_id": r.target_user_id, "target_name": names.get(r.target_user_id, ""),
             "status": r.status, "create_time": r.create_time.isoformat() if r.create_time else None}
            for r in rows
        ]}

    @staticmethod
    def revoke_share(db: Session, pid: int, target_user_id: int, user: User) -> dict:
        p = UserPaperService._get_owned(db, pid, user)
        share = db.scalar(select(PaperShare).where(
            PaperShare.paper_id == pid, PaperShare.target_user_id == target_user_id))
        if share is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="分享记录不存在")
        share.status = PaperShareStatus.REVOKED
        db.commit()
        return {"message": "已撤销对该用户的发布"}

    # ---------- 分享给我的 + 收藏 ----------

    @staticmethod
    def list_shared_to_me(db: Session, user: User, page: int = 1, page_size: int = 20) -> dict:
        """分享给我的试卷（ACTIVE）：含发布者昵称；概要脱敏（题目需调详情接口）。"""
        rows = list(db.execute(
            select(PaperShare, ExamPaper)
            .join(ExamPaper, ExamPaper.id == PaperShare.paper_id)
            .where(PaperShare.target_user_id == user.id, PaperShare.status == PaperShareStatus.ACTIVE)
            .order_by(PaperShare.create_time.desc())
            .offset((page - 1) * page_size).limit(page_size)
        ).all())
        total = db.scalar(
            select(func.count(PaperShare.id)).where(
                PaperShare.target_user_id == user.id, PaperShare.status == PaperShareStatus.ACTIVE)
        ) or 0
        owners = UserPaperService._names(db, {p.creator_id for _, p in rows})
        return {
            "page": page, "page_size": page_size, "total": int(total or 0),
            "items": [
                {**UserPaperService._paper_brief(p),
                 "publisher_name": owners.get(p.creator_id, ""),
                 "share_time": s.create_time.isoformat() if s.create_time else None}
                for s, p in rows
            ],
        }

    @staticmethod
    def shared_detail(db: Session, pid: int, user: User) -> dict:
        """被分享试卷概要（脱敏：不含答案；仅 ACTIVE 分享可看）。"""
        share = db.scalar(select(PaperShare).where(
            PaperShare.paper_id == pid, PaperShare.target_user_id == user.id,
            PaperShare.status == PaperShareStatus.ACTIVE))
        if share is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="试卷不存在或分享已撤销")
        p = PaperRepo.get_by_id(db, pid)
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="试卷不存在")
        detail = PaperService.get(db, pid)
        # 脱敏：去掉题目答案/解析（保留题干/选项/分值供预览）
        for q in detail.get("questions", []):
            q.pop("answer", None)
            q.pop("analysis", None)
            if isinstance(q.get("options"), list):
                for o in q["options"]:
                    o.pop("is_correct", None)
        return detail

    @staticmethod
    def copy_shared(db: Session, pid: int, user: User) -> dict:
        """收藏副本：复制试卷 + 题目快照到我的试卷库（source_paper_id 记录来源）。"""
        share = db.scalar(select(PaperShare).where(
            PaperShare.paper_id == pid, PaperShare.target_user_id == user.id,
            PaperShare.status == PaperShareStatus.ACTIVE))
        if share is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="试卷不存在或分享已撤销")
        src = PaperRepo.get_by_id(db, pid)
        if src is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="试卷不存在")
        items = [(q.question_id, q.score, q.seq) for q in PaperRepo.list_questions(db, pid)]
        copy = PaperRepo.create_with_questions(
            db,
            paper_kwargs={
                "name": f"{src.name}（收藏）",
                "total_score": src.total_score,
                "pass_score": src.pass_score,
                "duration": src.duration,
                "question_count": src.question_count,
                "difficulty_ratio": None,
                "gen_mode": src.gen_mode,
                "status": PaperStatus.DRAFT,
                "creator_id": user.id,
                "source_paper_id": src.id,
            },
            items=items,
        )
        return UserPaperService._paper_brief(copy)

    # ---------- Word 导出 ----------

    @staticmethod
    def export_word(db: Session, pid: int, user: User, with_answers: bool) -> bytes:
        """试卷另存为 Word（python-docx）：仅题目版 / 含答案版。"""
        p = PaperRepo.get_by_id(db, pid)
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="试卷不存在")
        detail = PaperService.get(db, pid)
        try:
            from docx import Document
            from docx.shared import Pt
        except ImportError:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="服务端缺少 python-docx 依赖")

        doc = Document()
        doc.add_heading(p.name, level=0)
        doc.add_paragraph(
            f"总分 {p.total_score} 分 · 合格线 {p.pass_score} 分 · 时长 {p.duration} 分钟 · 共 {p.question_count} 题"
            + ("（含答案版）" if with_answers else "（仅题目版）")
        )
        from ..model.question import QuestionType
        type_label = {
            QuestionType.SINGLE: "单选题", QuestionType.MULTIPLE: "多选题",
            QuestionType.JUDGE: "判断题", QuestionType.FILL: "填空题",
            QuestionType.SUBJECTIVE: "解答题",
        }
        seq = 0
        for q in detail.get("questions", []):
            seq += 1
            p_run = doc.add_paragraph()
            run = p_run.add_run(f"{seq}. [{type_label.get(q.get('type'), q.get('type'))}] "
                                f"（{q.get('score', '')}分） {q.get('content', '')}")
            run.font.size = Pt(11)
            for o in q.get("options") or []:
                doc.add_paragraph(f"  {o.get('label', '')}. {o.get('content', '')}")
            if with_answers:
                doc.add_paragraph(f"答案：{q.get('answer', '')}")
                if q.get("analysis"):
                    doc.add_paragraph(f"解析：{q.get('analysis')}")
        buf = __import__("io").BytesIO()
        doc.save(buf)
        return buf.getvalue()

    @staticmethod
    def _names(db: Session, ids: set[int]) -> dict[int, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        from ..model.user import User as _U
        rows = db.execute(select(_U.id, _U.name, _U.username).where(_U.id.in_(ids))).all()
        return {uid: (name or username) for uid, name, username in rows}
