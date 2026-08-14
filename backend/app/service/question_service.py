"""题库（E01）业务逻辑。

约定（对齐 DATABASE.md §6.1 审核状态机）：
- 人工录入 source=manual，直接以 status=APPROVED 入库；
- AI 生成 source=ai，一律 status=PENDING，经 E02 审核流转。
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..model.paper import ExamPaperQuestion
from ..model.question import Question, QuestionStatus, QuestionType
from ..repository import question_repo
from ..schema.question import QuestionCreate


class QuestionService:
    @staticmethod
    def _validate_answers(type_: str, options: list[str] | None, answer: str) -> None:
        """基础校验：按题型校验选项与答案格式（约定固化于 DATABASE.md §6.1 题型作答约定）。"""
        if type_ in (QuestionType.SINGLE, QuestionType.MULTIPLE):
            if not options:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="单选/多选必须提供选项")
            # 选项标签取首字母大写，支持 "A. xxx" / "A xxx" / "A" 三种写法
            labels = {opt[0].upper() for opt in options if opt and opt[0].isalpha()}
            if type_ == QuestionType.SINGLE:
                if answer.strip().upper() not in labels:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="单选答案必须是选项标签之一")
            else:  # MULTIPLE，答案形如 "A,B"
                for part in answer.replace("，", ",").split(","):
                    part = part.strip().upper()
                    if not part or part not in labels:
                        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"多选答案包含非法选项：{part}")
        elif type_ == QuestionType.JUDGE:
            # 判断固定选项 ["A 正确","B 错误"]，答案 A 或 B
            if answer.strip().upper() not in ("A", "B"):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="判断题答案必须是 A(正确) 或 B(错误)")
            if options is not None:
                labels = [o[0].upper() for o in options if o and o[0].isalpha()]
                if labels != ["A", "B"]:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="判断题选项须为 [\"A 正确\", \"B 错误\"]")
        elif type_ == QuestionType.FILL:
            # 填空多空用分号分隔，每空不能为空
            blanks = [p.strip() for p in answer.replace("；", ";").split(";")]
            if any(not b for b in blanks):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="填空题多空答案用分号分隔，每空不能为空")
        elif type_ == QuestionType.SUBJECTIVE:
            # 解答题：无选项；参考答案非空，分号分隔要点，每要点不能为空
            points = [p.strip() for p in answer.replace("；", ";").split(";")]
            if any(not p for p in points):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="解答题参考答案用分号分隔要点，每个要点不能为空")

    @staticmethod
    def create(db: Session, payload: QuestionCreate, operator_id: int) -> dict:
        QuestionService._validate_answers(payload.type, payload.options, payload.answer)
        q = question_repo.QuestionRepo.create(
            db,
            type=payload.type,
            content=payload.content,
            options=payload.options,
            answer=payload.answer,
            analysis=payload.analysis,
            knowledge_point=payload.knowledge_point,
            difficulty=payload.difficulty,
            source="manual",
            source_law_title=payload.source_law_title,
            source_article_no=payload.source_article_no,
            status=QuestionStatus.APPROVED,  # 人工录入直接通过
        )
        from ..utils.audit import write_audit
        write_audit(db, q, "question_create", target_type="question", target_id=q.id,
                    detail=f"type={q.type} kp={q.knowledge_point}")
        return _to_dict(q)

    @staticmethod
    def update(db: Session, qid: int, payload, operator_id: int) -> dict:
        q = question_repo.QuestionRepo.get_by_id(db, qid)
        if q is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="题目不存在")
        fields = payload.model_dump(exclude_unset=True)
        if "answer" in fields or "options" in fields or "type" in fields:
            QuestionService._validate_answers(
                fields.get("type", q.type),
                fields.get("options", q.options),
                fields.get("answer", q.answer),
            )
        q = question_repo.QuestionRepo.update(db, q, **fields)
        from ..utils.audit import write_audit
        write_audit(db, q, "question_update", target_type="question", target_id=qid,
                    detail=f"fields={','.join(sorted(fields))}")
        return _to_dict(q)

    @staticmethod
    def delete(db: Session, qid: int) -> None:
        q = question_repo.QuestionRepo.get_by_id(db, qid)
        if q is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="题目不存在")
        # 引用检查（#3）：被任何试卷引用（含 DRAFT/PUBLISHED）的题目不可删。
        # 否则进行中考试阅卷静默跳过该题 → total_score 虚高、成绩判定失真且无追溯。
        in_paper = (
            db.scalar(
                select(ExamPaperQuestion.id)
                .where(ExamPaperQuestion.question_id == qid)
                .limit(1)
            )
            is not None
        )
        if in_paper:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="题目已被试卷引用，不可删除（请先在试卷中移除该题）",
            )
        question_repo.QuestionRepo.delete(db, q)
        from ..utils.audit import write_audit
        write_audit(db, q, "question_delete", target_type="question", target_id=qid,
                    detail=f"type={q.type} content={str(q.content)[:40]}")

    @staticmethod
    def get(db: Session, qid: int) -> dict:
        q = question_repo.QuestionRepo.get_by_id(db, qid)
        if q is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="题目不存在")
        return _to_dict(q)

    @staticmethod
    def list_page(db: Session, **filters) -> dict:
        items, total = question_repo.QuestionRepo.list_page(db, **filters)
        return {
            "page": filters.get("page", 1),
            "page_size": filters.get("page_size", 20),
            "total": total,
            "items": [_to_dict(q) for q in items],
        }

    # ---------- Excel 批量导入/导出 ----------

    @staticmethod
    def export_all(db: Session) -> list[dict]:
        """导出全部题目（按 id 正序）为 _to_dict 结构列表，供 xlsx 序列化。"""
        rows = db.scalars(
            select(Question).order_by(Question.id.asc())
        ).all()
        return [_to_dict(q) for q in rows]

    @staticmethod
    def import_rows(db: Session, items: list[dict], operator_id: int) -> dict:
        """批量导入题目：行级答案格式校验（全部通过才入库，单事务）。

        返回 {"imported": n, "errors": [{"row","error"}]}；
        任一行的答案格式不合法（_validate_answers）→ 整批不入库（与 AI 出题先全校验约定一致）。
        """
        # 先全校验：答案/选项格式
        for i, item in enumerate(items, start=2):
            try:
                QuestionService._validate_answers(item["type"], item["options"], item["answer"])
            except HTTPException as exc:
                return {"imported": 0, "errors": [{"row": i, "error": f"答案校验失败：{exc.detail}"}]}
        # 单事务批量入库（source=manual、直接 APPROVED，与手工录入一致）
        rows = [
            Question(
                type=item["type"],
                content=item["content"],
                options=item["options"],
                answer=item["answer"],
                analysis=item["analysis"],
                knowledge_point=item["knowledge_point"],
                difficulty=item["difficulty"],
                source="manual",
                status=QuestionStatus.APPROVED,
            )
            for item in items
        ]
        if rows:
            db.add_all(rows)
            db.commit()
            for q in rows:
                db.refresh(q)
        return {"imported": len(rows), "errors": []}


def _to_dict(q) -> dict:
    return {
        "id": q.id,
        "batch_id": q.batch_id,
        "type": q.type,
        "content": q.content,
        "options": q.options,
        "answer": q.answer,
        "analysis": q.analysis,
        "knowledge_point": q.knowledge_point,
        "difficulty": q.difficulty,
        "source": q.source,
        "sources": q.sources,
        "source_law_title": q.source_law_title,
        "source_article_no": q.source_article_no,
        "status": q.status,
        "reviewer": q.reviewer,
        "review_note": q.review_note,
        "interference_verified": q.interference_verified,
        "rewrite_of": q.rewrite_of,
        "rewrite_feedback": q.rewrite_feedback,
        "create_time": q.create_time.isoformat() if q.create_time else None,
        "update_time": q.update_time.isoformat() if q.update_time else None,
    }
