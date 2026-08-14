"""E02 AI 出题服务（对齐 DATABASE.md §6.1 状态机 与 AI_SOLUTION §6 出题流程）。

核心流程：BM25 检索法规条款 → Prompt 构造 → LLM 输出 JSON → Pydantic 校验（失败重试）
→ 逐题规范化/溯源校验 → 以 source=ai、status=PENDING 批量入库（同 batch_id 一批）。

入库状态机（DATABASE.md §6.1）：AI 生成一律 status=PENDING 入草稿，经 E02 审核后
转 APPROVED/REJECTED；本模块只负责「生成→草稿」这段。
"""
from __future__ import annotations

import re
import uuid

import jieba

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.law_corpus import load_corpus
from ..ai.llm_client import LLMError, chat_json
from ..ai.prompts import _allocate, build_generate_prompt, build_rewrite_prompt
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


def _verify_distractor_grounding(
    options: list[str] | None, articles: list[dict], answer: str
) -> bool:
    """干扰项溯源自动校验（_drafts/4-AI出题专项 §4 落地）。

    对 SINGLE/MULTIPLE 的每个【干扰项】（非答案标签项），检查其文本是否在检索条款
    content 中存在关键片段（≥4 字的连续子串或 ≥2 个 ≥2 字关键词命中）。
    全部干扰项都无依据 → 返回 False（调用方不置 interference_verified，交由人工核对）；
    至少一个干扰项有依据 → True（自动置位 interference_verified=1）。

    判断依据：选项正文（去掉字母前缀）与条款全文做子串/关键词重叠检查。
    """
    if not options:
        return True  # 无选项题型（判断/填空/解答）无干扰项概念，直接视为通过
    ans_labels = {p.strip().upper() for p in answer.replace("，", ",").split(",") if p.strip()}
    article_text = " ".join(a.get("content") or "" for a in articles)
    if not article_text:
        return False
    grounded = 0
    total = 0
    for opt in options:
        body = re.sub(r"^[A-Za-z][.、．)）\s:：]*", "", opt).strip()
        if not body:
            continue
        # 跳过答案标签对应的选项（只校验干扰项）
        label_m = re.match(r"^([A-Za-z])[.、．)）\s:：]", opt)
        if label_m and label_m.group(1).upper() in ans_labels:
            continue
        total += 1
        # 关键片段：≥4 字连续子串在条款中出现
        if len(body) >= 4 and body[:4] in article_text:
            grounded += 1
            continue
        # 关键词：jieba 分词后 ≥2 字词至少 2 个命中条款
        words = [w for w in jieba.lcut(body) if len(w) >= 2 and w.strip()]
        hits = sum(1 for w in words if w in article_text)
        if hits >= 2:
            grounded += 1
    if total == 0:
        return True  # 全是答案项（如只有 2 选项的题），无干扰项可校验
    return grounded >= 1


def _plan_chunks(allocation: list[tuple[str, int]], chunk_size: int) -> list[list[tuple[str, int]]]:
    """把全局题型配额切成 ≤chunk_size 的分轮配额，返回分轮列表（各轮求和 = 全局配额）。

    保证连续同类型配额尽量同轮、跨轮只拆同一类型的余量，避免一轮混合过多题型。
    例如 [(S,8),(M,8),(J,7),(F,7)]、chunk=20 → [[(S,8),(M,8),(J,4)], [(J,3),(F,7)]]。
    仅当 count > gen_chunk_size 时走分轮；单轮内配额与旧版 _allocate(types,count) 完全一致。
    """
    pending = list(allocation)
    chunks: list[list[tuple[str, int]]] = []
    while pending:
        chunk: list[tuple[str, int]] = []
        room = chunk_size
        while pending and room > 0:
            t, n = pending[0]
            take = min(n, room)
            chunk.append((t, take))
            room -= take
            if take < n:
                pending[0] = (t, n - take)  # 本类型剩余留给下一轮
            else:
                pending.pop(0)
        chunks.append(chunk)
    return chunks


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
    answer = answer_raw if type_ in (QuestionType.FILL, QuestionType.SUBJECTIVE) else answer_raw.upper()
    options = data.get("options")
    if type_ == QuestionType.JUDGE:
        options = ["A 正确", "B 错误"]
    elif type_ in (QuestionType.FILL, QuestionType.SUBJECTIVE):
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

        # 0) 入参归一：知识点与参考文档至少其一（参考文档限定出题范围，E02 增强）
        kp = (payload.knowledge_point or "").strip()
        ref = (payload.reference_text or "").strip()
        ref_title = (payload.reference_title or "").strip() or "上传参考文档"
        if not kp and not ref:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="请填写知识点或上传参考文档")
        topic = kp or ref_title  # 用于 prompt 任务行与每题 knowledge_point 兜底

        # 1) 检索：优先限定法规，无结果则降级全库检索（top_k 放宽）。
        #    有参考文档时检索词取知识点或文档前 64 字；仍无结果允许仅凭文档出题。
        #    难度过滤：按 payload.difficulty 优先取同难度条款（_drafts/4 §3 落地）。
        search_term = kp or ref[:64]
        articles = corpus.search(search_term, top_k=6, law_title=payload.law_title,
                                 difficulty=payload.difficulty)
        if not articles:
            articles = corpus.search(search_term, top_k=8, difficulty=payload.difficulty)
        if not articles and ref:
            articles = []  # 有参考文档时允许仅凭文档出题
        if not articles:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="未检索到相关法规条款，请更换知识点或上传参考文档"
            )

        # 2) 题型配额 + 分轮：单轮 ≤ gen_chunk_size，避免单次 LLM 输出超长被截断导致 JSON 解析失败。
        #    count ≤ chunk 走单次调用（配额与旧版一致，回归安全）；count > chunk 拆成多轮，
        #    各轮独立调用 LLM，结果合并进同一 batch_id（用户侧仍是一个批次）。
        allocation = _allocate(payload.types, payload.count)
        plans: list[list[tuple[str, int]]] = (
            [allocation]
            if payload.count <= settings.gen_chunk_size
            else _plan_chunks(allocation, settings.gen_chunk_size)
        )
        n_plans = len(plans)

        # 3) LLM 生成 + Pydantic 校验：解析失败或题量不足自动重试，仍失败抛 502
        #    负样本回流（_drafts/4 §5）：注入最近驳回反例，规避同类问题
        from ..ai.rejected_examples import load_recent_examples
        rejected_examples = load_recent_examples()
        questions: list[GenQuestion] = []
        for plan_i, plan in enumerate(plans, 1):
            plan_total = sum(n for _, n in plan)
            system, user = build_generate_prompt(
                topic,
                articles,
                payload.types,
                payload.difficulty,
                plan_total,
                allocation=plan,
                reference_text=ref or None,
                reference_title=ref_title or None,
                rejected_examples=rejected_examples or None,
            )
            # 单轮沿用「≥gen_min_count」的宽松验收（旧版行为不变）；
            # 分轮时须凑够本轮配额，否则整批题量不符预期。
            min_count = settings.gen_min_count if n_plans == 1 else plan_total
            out: GenOutput | None = None
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    raw = await chat_json(system, user)
                    out = GenOutput.model_validate(raw)
                except (LLMError, ValidationError):
                    if attempt < _MAX_ATTEMPTS:
                        continue
                    raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="AI 输出不符合要求")
                got = list(out.questions)
                if len(got) >= min_count:
                    questions.extend(got)
                    break
                if attempt < _MAX_ATTEMPTS:
                    continue
                round_hint = f"（第 {plan_i}/{n_plans} 轮）" if n_plans > 1 else ""
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        f"AI 输出不符合要求{round_hint}（题量不足：{len(got)} 题，"
                        f"要求{'至少 ' if n_plans == 1 else ''}{min_count} 题）"
                    ),
                )

        # 4) 逐题规范化 + 校验（题型/难度/答案/溯源）
        #    【先全部校验、再统一入库】——任何一题校验失败都不产生任何落库，
        #    避免逐题 commit 留下半批孤儿 PENDING 草稿（#8）。
        batch_id = "ai_" + uuid.uuid4().hex[:12]
        law_titles = set(corpus.law_titles)
        prepared: list[dict] = []
        # 批次内题干去重（AI_SOLUTION §6.1「去重与完整性检查」落地）：
        # 规范化题干（去空白/标点）做集合判重，防止同批重复题
        seen_contents: set[str] = set()
        for i, q in enumerate(questions):
            data = q.model_dump() if hasattr(q, "model_dump") else dict(q)
            type_ = str(data.get("type") or "").strip().upper()
            difficulty = str(data.get("difficulty") or "").strip().upper()
            knowledge_point = (str(data.get("knowledge_point") or topic)).strip()
            content = str(data.get("content") or "").strip()

            # 批次内去重：规范化题干（去空白）重复则跳过该题（不影响批次数量的宽松验收）
            content_key = re.sub(r"\s+", "", content)
            if content_key in seen_contents:
                logger.warning("批次内重复题干跳过：%s", content[:40])
                continue
            seen_contents.add(content_key)
            # FILL/SUBJECTIVE 答案为自由文本（可含小写/数字），不做大写归一；其余题型答案收敛大写
            answer_raw = str(data.get("answer") or "").strip()
            answer = answer_raw if type_ in (QuestionType.FILL, QuestionType.SUBJECTIVE) else answer_raw.upper()
            options = data.get("options")
            analysis = (data.get("analysis") or "").strip() or None

            # 题型/难度合法性 + 题干非空
            if type_ not in (QuestionType.SINGLE, QuestionType.MULTIPLE, QuestionType.JUDGE,
                             QuestionType.FILL, QuestionType.SUBJECTIVE):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"第{i + 1}题题型不合法：{type_}")
            if difficulty not in _DIFFICULTY_ALLOWED:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"第{i + 1}题难度不合法：{difficulty}")
            if not content:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"第{i + 1}题题干为空")

            # JUDGE 强制固定选项；FILL/SUBJECTIVE 置空 options；再走答案/选项格式校验
            if type_ == QuestionType.JUDGE:
                options = ["A 正确", "B 错误"]
            elif type_ in (QuestionType.FILL, QuestionType.SUBJECTIVE):
                options = None
            try:
                QuestionService._validate_answers(type_, options, answer)
            except HTTPException as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"第{i + 1}题校验失败：{exc.detail}")

            # 溯源：缺失/为空则从检索条款整对补全；有参考文档时兜底锚定到参考文档，仍无则 400。
            # 整对替换避免跨法规错配（如保留 LLM 的 title + 取另一部法规的条号）。
            src_title = str(data.get("source_law_title") or "").strip()
            src_article_no = str(data.get("source_article_no") or "").strip()
            if not src_title or not src_article_no:
                pick = _pick_source(articles, knowledge_point, src_title or None)
                if pick is None and ref:
                    src_title, src_article_no = ref_title, "（上传参考文档）"
                elif pick is None:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="题目缺少法规溯源")
                else:
                    src_title, src_article_no = pick["law_title"], pick["article_no"]
            # 主要溯源法规必须在知识库内（锚定到参考文档的 title 豁免）
            if src_title != ref_title and src_title not in law_titles:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="溯源法规不在知识库")
            sources = _normalize_sources(data.get("sources"), src_title, src_article_no)

            # 干扰项溯源自动校验（_drafts/4 §4）：干扰项在检索条款中有依据 → 自动置位
            interference_verified = 1 if _verify_distractor_grounding(options, articles, answer) else 0

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
                    "interference_verified": interference_verified,
                    "status": QuestionStatus.PENDING,
                }
            )

        question_repo.QuestionRepo.create_batch(db, prepared)  # 单事务：整批或整批无

        from ..model.user import User
        from ..utils.audit import write_audit
        operator = db.get(User, operator_id)
        write_audit(db, operator, "ai_generate", target_type="question", target_id=batch_id,
                    detail=f"kp={topic} count={len(prepared)} difficulty={payload.difficulty}")

        return {
            "batch_id": batch_id,
            "count": len(prepared),
            "knowledge_point": topic,
            "difficulty": payload.difficulty,
        }

    @staticmethod
    async def rewrite(db: Session, qid: int, payload: RewriteIn, operator_id: int) -> dict:
        """按驳回意见 AI 重写已驳回的 AI 题，就地替换原题内容后回到 PENDING 草稿。

        - 仅 source=ai 且 status=REJECTED 可重写；就地覆盖题干/选项/答案/解析，状态回到 PENDING 重新审核，
          不新建批次、不产生新题（对齐「重新生成后就地替换」的确认语义）；
        - 原题已有「已通过」修订版时拒绝（409，防同一逻辑题重复入卷）；
          存量「待审」修订版（旧独立批次设计遗留）不阻断，落库时自动顶替为 REJECTED；
        - rewrite_feedback 存修订要求，清驳回意见 review_note，重置 interference_verified 需重新核对；
        - LLM 输出不合要求自动重试（形状/题型漂移/未实质修订等），仍失败抛 502。
        """
        q = question_repo.QuestionRepo.get_by_id(db, qid)
        if q is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="题目不存在")
        if q.source != QuestionSource.AI:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="仅可重写 AI 生成题目")
        if q.status != QuestionStatus.REJECTED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="仅可重写已驳回（REJECTED）的题目")
        # 就地替换语义：已通过的修订版已取代本原题，禁止再重写；待审修订版在落库时自动顶替，不再 409 阻断
        if question_repo.QuestionRepo.has_approved_rewrite(db, qid):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="该题已有已通过的修订版，请先处理修订版")

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

        try:
            # 顶掉存量待审修订版（旧「独立批次」设计遗留），避免同一逻辑题出现两个待审版本
            legacy = question_repo.QuestionRepo.get_pending_rewrite(db, q.id)
            if legacy is not None:
                legacy.status = QuestionStatus.REJECTED
                legacy.review_note = "被新一次重写顶替"
            # 就地替换：覆盖原题内容并回到「待审核」，批次不变
            question_repo.QuestionRepo.update(
                db,
                q,
                type=final["type"],
                content=final["content"],
                options=final["options"],
                answer=final["answer"],
                analysis=final["analysis"],
                knowledge_point=final["knowledge_point"],
                difficulty=final["difficulty"],
                sources=final["sources"],
                source_law_title=final["source_law_title"],
                source_article_no=final["source_article_no"],
                status=QuestionStatus.PENDING,  # 重新进入审核队列
                review_note=None,               # 清掉旧的驳回意见
                rewrite_feedback=payload.feedback,
                interference_verified=0,        # 内容已变，需重新核对干扰项
                rewrite_of=None,                # 就地替换，不再是「某题的修订版」
            )
        except IntegrityError:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, detail="该题已有待审核的修订版，请先处理")
        return _to_dict(q)

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
