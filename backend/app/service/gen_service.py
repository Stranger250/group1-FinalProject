"""E02 AI 出题服务（对齐 DATABASE.md §6.1 状态机 与 AI_SOLUTION §6 出题流程）。

核心流程：BM25 检索法规条款 → Prompt 构造 → LLM 输出 JSON → Pydantic 校验（失败重试）
→ 逐题规范化/溯源校验 → 以 source=ai、status=PENDING 批量入库（同 batch_id 一批）。

入库状态机（DATABASE.md §6.1）：AI 生成一律 status=PENDING 入草稿，经 E02 审核后
转 APPROVED/REJECTED；本模块只负责「生成→草稿」这段。
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.law_corpus import load_corpus
from ..ai.llm_client import LLMError, chat_json
from ..ai.prompts import build_generate_prompt, build_rewrite_prompt
from ..core.config import get_settings
from ..model.question import Question, QuestionSource, QuestionStatus, QuestionType
from ..repository import question_repo
from ..schema.ai import GenOutput, GenQuestion, GenRequest, RewriteIn
from ..service.question_service import QuestionService

# 难度合法值（LLM 输出的 difficulty 是自由字符串，入库前必须收敛到枚举）
_DIFFICULTY_ALLOWED = ("EASY", "MEDIUM", "HARD")
# LLM 解析/题量不达标时的重试次数（AI_SOLUTION §6.3：解析失败自动重试，最多 2 次）
_MAX_ATTEMPTS = 3


def _to_dict(q: Question) -> dict:
    """ORM → dict（与 E01 question_service._to_dict 逻辑一致，本地复制避免跨模块耦合）。"""
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


def _pick_source(articles: list[dict], knowledge_point: str, law_title: str | None) -> dict | None:
    """从检索结果中挑选主要溯源条款。

    优先取 content 命中知识点关键词的条款；其次按法规名匹配取任一条款；
    最后兜底取检索结果首条。返回 {"law_title","article_no","content"} 或 None。
    """
    kp = (knowledge_point or "").strip()
    # 1) 命中知识点关键词的条款（若指定了法规，限定在该法规内）
    if kp:
        for a in articles:
            if law_title and a["law_title"] != law_title:
                continue
            if kp in a["content"]:
                return a
    # 2) 按法规名匹配的任意条款
    for a in articles:
        if law_title and a["law_title"] != law_title:
            continue
        return a
    # 3) 兜底：检索结果首条
    if articles:
        return articles[0]
    return None


def _normalize_sources(raw, title: str, article_no: str) -> list[dict]:
    """溯源明细规范化：过滤非法条目，并确保主要溯源（source_law_title/article_no）已含于列表。

    对齐 AI_SOLUTION §6.3：sources 逐项为 {role, law_title, article_no}；
    验收要求 sources 与 source_law_title/source_article_no 一致，故补入/置顶主要溯源。
    """
    out: list[dict] = []
    if isinstance(raw, list):
        for s in raw:
            if not isinstance(s, dict):
                continue
            law = str(s.get("law_title") or "").strip()
            art = str(s.get("article_no") or "").strip()
            if law and art:
                out.append(
                    {"role": str(s.get("role") or "answer").strip(), "law_title": law, "article_no": art}
                )
    if not any(x["law_title"] == title and x["article_no"] == article_no for x in out):
        out.insert(0, {"role": "answer", "law_title": title, "article_no": article_no})
    return out


class _RewriteRetry(Exception):
    """重写输出不合要求，触发带约束重试（内部异常，不直接进 HTTP 响应）。"""


def _extract_single_question(raw: dict) -> dict:
    """从 LLM 响应提取单题 dict，兼容 {questions:[...]} 与裸单题对象两种形状。"""
    qs = raw.get("questions")
    if isinstance(qs, list) and qs:
        return qs[0]
    if isinstance(raw, dict) and raw.get("content"):
        return raw
    raise _RewriteRetry("输出形状不合法（应为一个题目对象或 questions 数组）")


def _finalize_rewrite(
    gq: GenQuestion, original: Question, articles: list[dict], law_titles: set[str]
) -> dict:
    """重写题规范化/校验，返回可直接入库的字段 dict。

    强制题型/知识点与原题一致（prompt 已约束，此处兜底），难度默认原题可依输出调整；
    溯源从检索条款重新推导（不信任 LLM 的 source 字段，避免跨法规错配）。
    不合要求抛 _RewriteRetry。
    """
    data = gq.model_dump() if hasattr(gq, "model_dump") else dict(gq)
    type_ = str(data.get("type") or "").strip().upper()
    if type_ != original.type:
        raise _RewriteRetry(f"题型必须保持与原题一致：{original.type}")
    content = str(data.get("content") or "").strip()
    if not content:
        raise _RewriteRetry("题干为空")
    difficulty = str(data.get("difficulty") or "").strip().upper() or original.difficulty
    if difficulty not in _DIFFICULTY_ALLOWED:
        difficulty = original.difficulty
    answer_raw = str(data.get("answer") or "").strip()
    answer = answer_raw if type_ == QuestionType.FILL else answer_raw.upper()
    options = data.get("options")
    if type_ == QuestionType.JUDGE:
        options = ["A 正确", "B 错误"]
    elif type_ == QuestionType.FILL:
        options = None
    try:
        QuestionService._validate_answers(type_, options, answer)
    except HTTPException as exc:
        raise _RewriteRetry(f"答案/选项校验失败：{exc.detail}")

    pick = _pick_source(articles, original.knowledge_point, None)
    if pick is None:
        raise _RewriteRetry("无法从检索条款确定法规溯源")
    src_title, src_article_no = pick["law_title"], pick["article_no"]
    if src_title not in law_titles:
        raise _RewriteRetry("溯源法规不在知识库")
    sources = _normalize_sources(data.get("sources"), src_title, src_article_no)

    return {
        "type": type_,
        "content": content,
        "options": options,
        "answer": answer,
        "analysis": (data.get("analysis") or "").strip() or None,
        "knowledge_point": original.knowledge_point,
        "difficulty": difficulty,
        "source_law_title": src_title,
        "source_article_no": src_article_no,
        "sources": sources,
    }


class GenService:
    @staticmethod
    async def generate(db: Session, payload: GenRequest, operator_id: int) -> dict:
        """AI 生成一批题目并批量入库（source=ai、status=PENDING，同 batch_id）。

        operator_id：当前 question 表无 creator 字段，预留（后续审计可落库）；
        审核人于 E02 审核动作时写入 reviewer，此处不落库。
        """
        settings = get_settings()
        corpus = load_corpus()

        # 1) 检索：优先限定法规，无结果则降级全库检索（top_k 放宽）
        articles = corpus.search(payload.knowledge_point, top_k=6, law_title=payload.law_title)
        if not articles:
            articles = corpus.search(payload.knowledge_point, top_k=8)
        if not articles:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="未检索到相关法规条款，请更换知识点")

        # 2) 构造 Prompt（角色 + 知识条款 + 题型数量难度）
        system, user = build_generate_prompt(
            payload.knowledge_point, articles, payload.types, payload.difficulty, payload.count
        )

        # 3) LLM 生成 + Pydantic 校验：解析失败或题量不足自动重试，仍失败抛 502
        out: GenOutput | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                raw = await chat_json(system, user)
                out = GenOutput.model_validate(raw)
            except (LLMError, ValidationError):
                if attempt < _MAX_ATTEMPTS:
                    continue
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="AI 输出不符合要求")
            questions = list(out.questions)
            if len(questions) >= settings.gen_min_count:
                break  # 达到最低题量（≥5，PRD E02 验收）
            if attempt < _MAX_ATTEMPTS:
                continue
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail=f"AI 输出不符合要求（题量不足：{len(questions)} 题，要求至少 {settings.gen_min_count} 题）",
            )

        # 4) 逐题规范化 + 校验（题型/难度/答案/溯源）
        #    【先全部校验、再统一入库】——任何一题校验失败都不产生任何落库，
        #    避免逐题 commit 留下半批孤儿 PENDING 草稿（#8）。
        batch_id = "ai_" + uuid.uuid4().hex[:12]
        law_titles = set(corpus.law_titles)
        prepared: list[dict] = []
        for i, q in enumerate(questions):
            data = q.model_dump() if hasattr(q, "model_dump") else dict(q)
            type_ = str(data.get("type") or "").strip().upper()
            difficulty = str(data.get("difficulty") or "").strip().upper()
            knowledge_point = (str(data.get("knowledge_point") or payload.knowledge_point)).strip()
            content = str(data.get("content") or "").strip()
            # FILL 答案为自由文本（可含小写/数字），不做大写归一；其余题型答案收敛大写
            answer_raw = str(data.get("answer") or "").strip()
            answer = answer_raw if type_ == QuestionType.FILL else answer_raw.upper()
            options = data.get("options")
            analysis = (data.get("analysis") or "").strip() or None

            # 题型/难度合法性 + 题干非空
            if type_ not in (QuestionType.SINGLE, QuestionType.MULTIPLE, QuestionType.JUDGE, QuestionType.FILL):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"第{i + 1}题题型不合法：{type_}")
            if difficulty not in _DIFFICULTY_ALLOWED:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"第{i + 1}题难度不合法：{difficulty}")
            if not content:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"第{i + 1}题题干为空")

            # JUDGE 强制固定选项；FILL 置空 options；再走答案/选项格式校验
            if type_ == QuestionType.JUDGE:
                options = ["A 正确", "B 错误"]
            elif type_ == QuestionType.FILL:
                options = None
            try:
                QuestionService._validate_answers(type_, options, answer)
            except HTTPException as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"第{i + 1}题校验失败：{exc.detail}")

            # 溯源：缺失/为空则从检索条款整对补全，仍无则 400。
            # 整对替换避免跨法规错配（如保留 LLM 的 title + 取另一部法规的条号）。
            src_title = str(data.get("source_law_title") or "").strip()
            src_article_no = str(data.get("source_article_no") or "").strip()
            if not src_title or not src_article_no:
                pick = _pick_source(articles, knowledge_point, src_title or None)
                if pick is None:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="题目缺少法规溯源")
                src_title, src_article_no = pick["law_title"], pick["article_no"]
            # 主要溯源法规必须在知识库内
            if src_title not in law_titles:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="溯源法规不在知识库")
            sources = _normalize_sources(data.get("sources"), src_title, src_article_no)

            # 5) 入库（统一在循环后批量落库）：source=ai、status=PENDING、同批 batch_id、sources 存 JSON 列表
            prepared.append(
                {
                    "batch_id": batch_id,
                    "type": type_,
                    "content": content,
                    "options": options,
                    "answer": answer,
                    "analysis": analysis,
                    "knowledge_point": knowledge_point,
                    "difficulty": difficulty,
                    "source": QuestionSource.AI,
                    "sources": sources,
                    "source_law_title": src_title,
                    "source_article_no": src_article_no,
                    "status": QuestionStatus.PENDING,
                }
            )

        question_repo.QuestionRepo.create_batch(db, prepared)  # 单事务：整批或整批无

        return {
            "batch_id": batch_id,
            "count": len(prepared),
            "knowledge_point": payload.knowledge_point,
            "difficulty": payload.difficulty,
        }

    @staticmethod
    async def rewrite(db: Session, qid: int, payload: RewriteIn, operator_id: int) -> dict:
        """按驳回意见 AI 重写已驳回的 AI 题，产出修订版新题入 PENDING 草稿。

        - 仅 source=ai 且 status=REJECTED 可重写；原题状态不变（保留驳回留痕）；
        - 原题已存在待审/已通过修订版时拒绝（409，DB 层 uk_rewrite_pending 兜底并发）；
        - 修订版独立成新 batch（ai_ 前缀），rewrite_of 指向原题 id，rewrite_feedback 存修订要求；
        - LLM 输出不合要求自动重试（形状/题型漂移/未实质修订等），仍失败抛 502。
        """
        q = question_repo.QuestionRepo.get_by_id(db, qid)
        if q is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="题目不存在")
        if q.source != QuestionSource.AI:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="仅可重写 AI 生成题目")
        if q.status != QuestionStatus.REJECTED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="仅可重写已驳回（REJECTED）的题目")
        # 已存在待审/已通过修订版时不再重写：待审→防并发/重复草稿，已通过→防同一逻辑题重复入卷
        if question_repo.QuestionRepo.has_active_rewrite(db, qid):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="该题已存在修订版（待审或已通过），请先处理修订版")

        corpus = load_corpus()
        law_titles = set(corpus.law_titles)
        # 检索降级链：限定原法规（若在库）→ 全库知识点 → 全库原题干，仍无才 400
        law_title = q.source_law_title if q.source_law_title in law_titles else None
        articles = corpus.search(q.knowledge_point, top_k=6, law_title=law_title)
        if not articles:
            articles = corpus.search(q.knowledge_point, top_k=8)
        if not articles:
            articles = corpus.search((q.content or "")[:64], top_k=8)
        if not articles:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="未检索到相关法规条款，无法重写")

        system, user = build_rewrite_prompt(
            _to_dict(q), q.review_note or "", payload.feedback, articles
        )
        # 重试强化指令：LLM 首轮常被原题锚定而原样复述，追加强约束再试（对齐 AI_SOLUTION §6.3 重试口径）
        strengthen = (
            "\n\n【重要】你上一轮输出未能解决驳回问题（与原题完全一致或题型不符）。"
            "请严格按「驳回原因」与「本次修订要求」逐条修改，题干/选项/答案/解析至少一处实质变化，"
            "并逐项核对给定法规条款；不得原样复述原题。"
        )

        final: dict | None = None
        last_err: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                raw = await chat_json(system, user + (strengthen if attempt > 1 else ""))
                cand = _extract_single_question(raw)
                gq = GenQuestion.model_validate(cand)
                final = _finalize_rewrite(gq, q, articles, law_titles)
                # 防「原样复述」：题干/选项/答案/解析均未实质变化才视为未修订
                if (
                    final["content"] == q.content
                    and final["answer"] == q.answer
                    and final["analysis"] == q.analysis
                    and final["options"] == q.options
                ):
                    raise _RewriteRetry("重写结果与原题一致，未实质修订")
            except (_RewriteRetry, LLMError, ValidationError) as exc:
                last_err = exc
                if attempt < _MAX_ATTEMPTS:
                    continue
                hint = "（若题目本身无误，请直接复核通过，无需重写）" if isinstance(exc, _RewriteRetry) else ""
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"AI 重写失败：{last_err}{hint}")
            break

        batch_id = "ai_" + uuid.uuid4().hex[:12]
        try:
            new_q = question_repo.QuestionRepo.create(
                db,
                batch_id=batch_id,
                rewrite_of=q.id,
                rewrite_feedback=payload.feedback,
                type=final["type"],
                content=final["content"],
                options=final["options"],
                answer=final["answer"],
                analysis=final["analysis"],
                knowledge_point=final["knowledge_point"],
                difficulty=final["difficulty"],
                source=QuestionSource.AI,
                sources=final["sources"],
                source_law_title=final["source_law_title"],
                source_article_no=final["source_article_no"],
                status=QuestionStatus.PENDING,
            )
        except IntegrityError:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, detail="该题已存在待审核的修订版，请先处理")
        return _to_dict(new_q)

    @staticmethod
    def list_batches(db: Session) -> list[dict]:
        """按 batch_id 分组统计 AI 生成批次（仅 source=ai），pass_rate=approved/(approved+rejected)。"""
        rows = db.execute(
            select(
                Question.batch_id,
                func.count(Question.id),
                func.sum(case((Question.status == QuestionStatus.APPROVED, 1), else_=0)),
                func.sum(case((Question.status == QuestionStatus.REJECTED, 1), else_=0)),
                func.sum(case((Question.status == QuestionStatus.PENDING, 1), else_=0)),
                func.max(Question.id),
            )
            .where(Question.source == QuestionSource.AI, Question.batch_id.isnot(None))
            .group_by(Question.batch_id)
            .order_by(func.max(Question.id).desc())  # batch_id 为 ai_+随机hex，按字典序无时间意义，改用 id 序
        ).all()
        result: list[dict] = []
        for batch_id, total, approved, rejected, pending, _last_id in rows:
            approved, rejected, pending = int(approved or 0), int(rejected or 0), int(pending or 0)
            denom = approved + rejected
            result.append(
                {
                    "batch_id": batch_id,
                    "total": int(total),
                    "pending": pending,
                    "approved": approved,
                    "rejected": rejected,
                    "pass_rate": round(approved / denom, 4) if denom else 0.0,
                }
            )
        return result

    @staticmethod
    def list_batch(db: Session, batch_id: str) -> dict:
        """批次详情：题目完整列表 + 状态统计；批次不存在抛 404。"""
        items = list(
            db.scalars(
                select(Question)
                .where(Question.source == QuestionSource.AI, Question.batch_id == batch_id)
                .order_by(Question.id.asc())
            )
        )
        if not items:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="批次不存在")
        approved = sum(1 for q in items if q.status == QuestionStatus.APPROVED)
        rejected = sum(1 for q in items if q.status == QuestionStatus.REJECTED)
        pending = sum(1 for q in items if q.status == QuestionStatus.PENDING)
        denom = approved + rejected
        return {
            "batch_id": batch_id,
            "total": len(items),
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "pass_rate": round(approved / denom, 4) if denom else 0.0,
            "questions": [_to_dict(q) for q in items],
        }

    @staticmethod
    def stats(db: Session) -> dict:
        """AI 生成总体统计：总数/各状态数/通过率 + 批次明细。"""
        row = db.execute(
            select(
                func.count(Question.id),
                func.sum(case((Question.status == QuestionStatus.APPROVED, 1), else_=0)),
                func.sum(case((Question.status == QuestionStatus.REJECTED, 1), else_=0)),
                func.sum(case((Question.status == QuestionStatus.PENDING, 1), else_=0)),
                func.sum(case((Question.rewrite_of.isnot(None), 1), else_=0)),
            ).where(Question.source == QuestionSource.AI)
        ).one()
        total_ai = int(row[0])
        total_approved = int(row[1] or 0)
        total_rejected = int(row[2] or 0)
        total_pending = int(row[3] or 0)
        total_rewritten = int(row[4] or 0)
        denom = total_approved + total_rejected
        return {
            "total_ai": total_ai,
            "total_pending": total_pending,
            "total_approved": total_approved,
            "total_rejected": total_rejected,
            "total_rewritten": total_rewritten,
            "pass_rate": round(total_approved / denom, 4) if denom else 0.0,
            "batches": GenService.list_batches(db),
        }
