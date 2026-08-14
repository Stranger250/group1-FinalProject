# -*- coding: utf-8 -*-
"""考试统计与错题本（任务书 E07 考试统计分析 / E06 错题回顾 落地）。

设计：
- 统计口径：以【已交卷（SUBMITTED）】记录为准；无考试记录时返回空统计（不报错）；
- 通过率：PASS 记录数 / 已交卷记录数（exam_record.status=PASS）；
- 错题排行：exam_answer 中 is_correct=0 的题按出错次数降序（取前 N）；
- 知识点掌握度：以错题所属 knowledge_point 聚合，掌握度 = 该知识点正确作答次数 / 总作答次数；
- 全部为只读统计接口，不写库；分页仅用于错题明细（默认前 50）。
"""
from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..model.exam import ExamAnswer, ExamRecord, ExamRecordResultStatus, ExamRecordState
from ..model.question import Question


def exam_stats(db: Session, user_id: int | None = None,
               paper_id: int | None = None) -> dict:
    """考试统计：总览（记录数/通过率/平均分）+ 错题排行 + 知识点掌握度。

    user_id 为空 → 全站统计（ADMIN）；否则仅统计该用户（错题本数据源之一）。
    """
    conds = [ExamRecord.state == ExamRecordState.SUBMITTED]
    if user_id is not None:
        conds.append(ExamRecord.user_id == user_id)
    if paper_id is not None:
        conds.append(ExamRecord.paper_id == paper_id)

    records = list(db.scalars(select(ExamRecord).where(*conds)))
    total = len(records)
    passed = sum(1 for r in records if r.status == ExamRecordResultStatus.PASS)
    scores = [r.score for r in records if r.score is not None]

    # 错题排行：已交卷记录内的错误答案明细
    record_ids = [r.id for r in records]
    wrong: list[tuple[int, int]] = []  # (question_id, wrong_count)
    if record_ids:
        rows = db.execute(
            select(ExamAnswer.question_id, func.count(ExamAnswer.id))
            .where(ExamAnswer.record_id.in_(record_ids), ExamAnswer.is_correct == 0)
            .group_by(ExamAnswer.question_id)
            .order_by(func.count(ExamAnswer.id).desc())
            .limit(50)
        ).all()
        wrong = [(qid, cnt) for qid, cnt in rows]

    # 知识点掌握度：正确/总作答（含正确与错误，排除未作答占位空答案）
    kp_stats: dict[str, list[int]] = {}
    if record_ids:
        ans_rows = db.execute(
            select(ExamAnswer.question_id, ExamAnswer.is_correct)
            .where(ExamAnswer.record_id.in_(record_ids))
        ).all()
        qids = {qid for qid, _ in ans_rows}
        if qids:
            q_kp = {
                q.id: (q.knowledge_point or "未分类")
                for q in db.scalars(select(Question).where(Question.id.in_(qids)))
            }
            for qid, is_correct in ans_rows:
                kp = q_kp.get(qid, "未分类")
                bucket = kp_stats.setdefault(kp, [0, 0])
                bucket[1] += 1
                if is_correct == 1:
                    bucket[0] += 1
    knowledge = [
        {"knowledge_point": kp, "total": v[1], "correct": v[0],
         "mastery": round(v[0] / v[1], 4) if v[1] else 0.0}
        for kp, v in sorted(kp_stats.items(), key=lambda x: -x[1][0])
    ]

    return {
        "total_exams": total,
        "passed_exams": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "wrong_top": [{"question_id": qid, "wrong_count": cnt} for qid, cnt in wrong],
        "knowledge_mastery": knowledge,
    }


def wrong_book(db: Session, user_id: int, page: int = 1, page_size: int = 20) -> dict:
    """错题本：当前用户全部错误作答明细（去重题目 + 最近错误时间），分页。

    仅统计已交卷记录（SUBMITTED），按最近出错时间倒序。
    """
    rec_ids = db.scalars(
        select(ExamRecord.id).where(
            ExamRecord.user_id == user_id,
            ExamRecord.state == ExamRecordState.SUBMITTED,
        )
    ).all()
    rec_ids = list(rec_ids)
    if not rec_ids:
        return {"page": page, "page_size": page_size, "total": 0, "items": []}

    # 每个 (record_id, question_id) 最近的错误行（窗口函数取 rn=1）
    sub = (
        select(
            ExamAnswer.id.label("ans_id"),
            ExamAnswer.question_id.label("question_id"),
            ExamAnswer.correct_answer.label("correct_answer"),
            ExamAnswer.user_answer.label("user_answer"),
            func.row_number().over(
                partition_by=(ExamAnswer.record_id, ExamAnswer.question_id),
                order_by=ExamAnswer.id.desc(),
            ).label("rn"),
        )
        .where(ExamAnswer.record_id.in_(rec_ids), ExamAnswer.is_correct == 0)
        .subquery()
    )
    rows = db.execute(
        select(sub).where(sub.c.rn == 1)
        .order_by(sub.c.ans_id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    total = db.scalar(
        select(func.count()).select_from(sub).where(sub.c.rn == 1)
    ) or 0

    qids = {r.question_id for r in rows}
    q_map = {
        q.id: q for q in db.scalars(select(Question).where(Question.id.in_(qids or [0])))
    }
    items = []
    for r in rows:
        q = q_map.get(r.question_id)
        if q is None:
            continue
        items.append({
            "question_id": r.question_id,
            "type": q.type,
            "content": q.content,
            "options": q.options,
            "correct_answer": r.correct_answer,
            "user_answer": r.user_answer,
            "analysis": q.analysis,
            "knowledge_point": q.knowledge_point,
            "wrong_time": None,  # exam_answer 无时间列，明细按记录时间呈现由前端补
        })
    return {"page": page, "page_size": page_size, "total": total, "items": items}
