"""E02 AI 出题审核业务逻辑（对齐 DATABASE.md §6.1 审核状态机）。

状态机约定：
- AI 生成 source=ai 一律以 status=PENDING 入草稿，经审核转 APPROVED/REJECTED；
- PENDING / REJECTED：可按 action 审（REJECTED 允许复核纠正，如重新通过）；
- 任何驳回（REJECT）必须填写 review_note，否则 400（驳回须有依据，反哺生成侧）；
- DISABLED：不允许审核（400）。
- 人工录入 source != 'ai' 不在本服务审核范围（400）。
- interference_verified 仅在请求显式给出时更新，复核不静默清空人工核验结果。
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..model.question import QuestionSource, QuestionStatus
from ..repository.question_repo import QuestionRepo
from ..schema.ai import BatchReviewIn, ReviewIn

# 审核动作 -> 目标状态：APPROVE->APPROVED，REJECT->REJECTED（status 落库用后者）
_ACTION_STATUS = {"APPROVE": QuestionStatus.APPROVED, "REJECT": QuestionStatus.REJECTED}


class ReviewService:
    @staticmethod
    def _precheck(db: Session, q, payload: ReviewIn, reviewer_id: int) -> dict:
        """审核预检（不落库）：状态机校验 + 计算落库字段。任一题失败 → 整批不入库（#9）。

        O8：放开来源限制——AI 生成（source=ai）与普通用户手工提交（source=manual）均可审核；
        其余校验（DISABLED 拒审、驳回必填意见、修订版冲突）不变。
        """
        if q.status == QuestionStatus.DISABLED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="已停用题目不允许审核")
        # 存在待审/已通过的修订版时禁止直接复核原题通过，避免同一逻辑题重复入卷
        if payload.action == "APPROVE" and QuestionRepo.has_active_rewrite(db, q.id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="该题存在修订版本（待审或已通过），请处理修订版，勿直接复核原题",
            )
        # 任何驳回都必须填写审核意见（否则无法向生成侧反哺修正依据）
        if payload.action == "REJECT" and not payload.review_note:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="驳回必须填写审核意见")
        # PENDING/REJECTED/APPROVED 均可按 action 审；APPROVED 重复通过视为复核，幂等落库
        fields = payload.model_dump(exclude_unset=True)
        data = {
            "status": _ACTION_STATUS[payload.action],
            "reviewer": reviewer_id,
            "review_note": payload.review_note,
        }
        # interference_verified 仅在请求显式给出时更新，复核不静默清空人工核验结果
        if "interference_verified" in fields:
            data["interference_verified"] = int(fields["interference_verified"])
        return data

    @staticmethod
    def review_one(db: Session, qid: int, payload: ReviewIn, reviewer_id: int) -> dict:
        """审核单题，按状态机流转后返回题目完整 dict。"""
        q = QuestionRepo.get_by_id(db, qid)
        if q is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="题目不存在")
        data = ReviewService._precheck(db, q, payload, reviewer_id)
        q = QuestionRepo.update(db, q, **data)
        # 审计留痕（独立事务，失败不阻断）
        from ..utils.audit import write_audit
        write_audit(db, q, "question_review", target_type="question", target_id=qid,
                    detail=f"action={payload.action} note={payload.review_note or ''} reviewer={reviewer_id}")
        # 负样本回流：驳回时把题面+意见写入反例库（_drafts/4 §5，供后续出题规避同类问题）
        if payload.action == "REJECT":
            from ..ai.rejected_examples import add_rejected_example
            add_rejected_example(
                content=q.content, type_=q.type,
                knowledge_point=q.knowledge_point,
                review_note=payload.review_note or "",
            )
        return _to_dict(q)

    @staticmethod
    def review_batch(
        db: Session, batch_id: str, payload: BatchReviewIn, reviewer_id: int
    ) -> dict:
        """整批/部分审核：ids 为空则整批，否则仅审指定 id。

        返回 {"batch_id", "reviewed", "action"}。先对全部目标做状态机预检，
        全部通过后再单事务批量落库（update_many 一次 commit）——任一题校验失败
        则整批不落任何题目，避免「接口报错而部分题目已审核」的不一致（#9）。
        """
        questions = QuestionRepo.list_by_batch(db, batch_id)
        if not questions:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="该批次不存在题目")

        if payload.ids:
            # 仅审指定题目：校验均在批次内，缺失抛 404
            by_id = {q.id: q for q in questions}
            missing = [i for i in payload.ids if i not in by_id]
            if missing:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail=f"批次中不存在题目：{missing}",
                )
            targets = [by_id[i] for i in payload.ids]
        else:
            # 整批驳回必须填写审核意见，避免无依据批量打回
            if payload.action == "REJECT" and not payload.review_note:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail="整批驳回必须填写审核意见"
                )
            targets = questions

        # 先预检全部（BatchReviewIn 含 ReviewIn 全部字段，可直接复用单题校验）
        items = [(q, ReviewService._precheck(db, q, payload, reviewer_id)) for q in targets]
        # 单事务落库：要么全部生效、要么全部回滚
        QuestionRepo.update_many(db, items)
        return {"batch_id": batch_id, "reviewed": len(items), "action": payload.action}


def _to_dict(q) -> dict:
    """题目完整 dict（与 E01 输出结构一致）。"""
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
