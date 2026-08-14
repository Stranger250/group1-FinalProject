"""AI 智能助手（模块二）问答编排（A01 RAG 智能问答，SSE 流式）。

SSE 事件序（契约 §0.1）：meta → delta* → done；LLM 静默超时发 ping 保活。
  meta  {conversation_id, user_message_id, mode, confidence, citations, rewritten_used}
  delta {text}                                  # 逐增量
  ping  {type:"ping"}                           # LLM 60s 静默保活
  done  {answer_id, citations, grounding_score, synthetic}

编排（契约 §0.1 / 计划 M3）：
  ① 敏感词预检（api 层同步做，命中 400 不进检索/LLM）
  ② 解析/建会话 + 归属校验（api 层同步做，404 掩码）
  ③ 先落 user 消息行（断线不丢历史）
  ④ 规则改写（指代词/过短 → 最近 5 轮拼接），改写串进检索、原文进 BM25 双路
  ⑤ 检索经 asyncio.to_thread（embedding/rerank 同步阻塞）
  ⑥ refuse → 写拒答行，meta(空引用)+delta(话术)+done，不调 LLM
  ⑦ full/conservative → meta(citations) → LLM 流（60s ping）→ grounding 校验
     （越界 [n] 删除、无脚注置 0 不重生成）→ assistant+message_source 单事务落库
     → touch 会话 → done(answer_id, citations, grounding_score, synthetic=true)
  ⑧ 异常/断线：best-effort 写 FAILED/INTERRUPTED 态，再抛/再关（GeneratorExit 兜底）

并发：会话级 asyncio.Lock（同会话串行防历史竞态）；LLM 并发 Semaphore 背压；
同步检索统一放线程池（asyncio.to_thread），DB 写留事件循环。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from decimal import Decimal
from typing import Any, AsyncIterator

from fastapi import HTTPException, status

from ..ai.llm_client import LLMError, chat_stream
from ..ai.prompts import build_qa_prompt
from ..core.config import get_settings
from ..model.chat import MessageStatus, MessageRole
from ..rag.citations import RetrievedBlock, build_citations, display_score
from ..rag.rag_config import RAGParams
from ..rag.retriever import ACCESS_EMPLOYEE, get_retriever
from ..rag.rewriter import rewrite_query
from ..rag.sensitive import contains_sensitive
from ..repository.chat_repo import ConversationRepo, MessageRepo, MessageSourceRepo
from ..schema.chat import ChatIn

logger = logging.getLogger("qa_service")

# 拒答话术（mode=refuse 或检索为空时固定输出，不调 LLM）
_REFUSE_TEXT = (
    "抱歉，我没有在法规知识库中检索到与你问题相关的可靠依据，暂时无法给出有依据的答案。"
    "你可以换个说法描述问题，或从快捷提问中选择一个安全生产主题。"
)

# 引用脚注 [n]（LLM 生成，grounding 校验用）
_REF_RE = re.compile(r"\[(\d{1,3})\]")

# 会话级锁：{conversation_id: asyncio.Lock}（单事件循环，无需额外线程同步）
_CONV_LOCKS: dict[int, asyncio.Lock] = {}
# LLM 并发信号量（背压，防打满上游限流）
_LLM_SEMAPHORE = asyncio.Semaphore(get_settings().rag_llm_semaphore)


def _conv_lock(conv_id: int) -> asyncio.Lock:
    lock = _CONV_LOCKS.get(conv_id)
    if lock is None:
        lock = asyncio.Lock()
        _CONV_LOCKS[conv_id] = lock
    return lock


def _estimate_tokens(text: str) -> int:
    """中文 token 粗估：按 1.5 字/token，最少 1。"""
    return max(1, int(len(text) / 1.5))


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class QaService:
    # ---------- 预检 / 会话（api 层同步调用，出错走正常 HTTP 错误路径） ----------

    @staticmethod
    def resolve_conversation(db, user, payload: ChatIn):
        """返回 (conversation, is_new)。

        - payload.conversation_id 为空 → 新建会话（首问自动标题=message 前 20 字）；
        - 非空 → 归属校验（不存在/非本人统一 404 掩码）。
        """
        if payload.conversation_id is None:
            title = payload.message.strip()[:20] + ("…" if len(payload.message.strip()) > 20 else "")
            conv = ConversationRepo.create(db, user_id=user.id, title=title or "新会话")
            return conv, True
        conv = ConversationRepo.get_by_id(db, payload.conversation_id)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="会话不存在")
        return conv, False

    @staticmethod
    def persist_user_message(db, conv, message: str) -> tuple[int, list[str]]:
        """先落 user 消息行（COMMIT），返回 (消息 id, 改写前的历史问句)。

        历史问句在插入当前行之前取（规则改写只需上一轮及更早）。
        """
        history = MessageRepo.list_history_questions(db, conv.id, limit=get_settings().rag_max_rounds)
        msg = MessageRepo.create(
            db,
            conversation_id=conv.id,
            role=MessageRole.USER,
            content=message,
            token_count=_estimate_tokens(message),
            status=MessageStatus.SUCCESS,
        )
        return msg.id, history

    # ---------- SSE 流编排 ----------

    @staticmethod
    async def stream_qa(db, conv, user_msg_id: int, message: str,
                        history: list[str]) -> AsyncIterator[str]:
        """编排一次问答，逐条 yield SSE 文本行（meta → delta* → done）。"""
        settings = get_settings()
        retriever = get_retriever()

        async with _conv_lock(conv.id):
            # ④ 规则改写 → 改写串进检索、原文进 BM25 双路
            rw = rewrite_query(message, history, max_rounds=settings.rag_max_rounds)
            kw_queries = [message] if rw.rewritten_used else None

            # ⑤ 检索（同步阻塞 → 线程池）
            result = await asyncio.to_thread(retriever.search, rw.query, kw_queries, ACCESS_EMPLOYEE)
            blocks = result.blocks
            citations = build_citations(blocks)

            # ⑥ 拒答判定：RRF 置信度 refuse，或向量相似度低于绝对下限（检索到但无关），
            #    或检索为空 → 拒答（不调 LLM，防幻觉）
            low_sim = result.top_vec_sim < RAGParams.from_settings().vec_sim_floor
            eff_mode = "refuse" if low_sim or not blocks else result.mode
            if result.mode == "refuse" or low_sim or not blocks:
                text = _REFUSE_TEXT
                # 拒答不展示引用：低相似度时检索到的块是无依据的垃圾，citations 置空
                cite_out: list[dict] = []
                try:
                    QaService._persist_assistant(
                        db, conv, user_msg_id, text, [], grounding=0.0,
                        status=MessageStatus.SUCCESS,
                    )
                    ConversationRepo.touch(db, conv)
                except Exception:  # noqa: BLE001 —— 拒答落库失败不阻断回答
                    logger.exception("拒答消息落库失败")
                yield _sse("meta", {
                    "conversation_id": conv.id, "user_message_id": user_msg_id,
                    "mode": eff_mode, "confidence": round(result.confidence, 4),
                    "citations": cite_out, "rewritten_used": rw.rewritten_used,
                })
                yield _sse("delta", {"text": text})
                yield _sse("done", {
                    "answer_id": 0, "citations": cite_out,
                    "grounding_score": 0.0, "synthetic": True,
                })
                return

            # ⑦ full/conservative → meta 先出（前端先渲染引用依据）
            yield _sse("meta", {
                "conversation_id": conv.id, "user_message_id": user_msg_id,
                "mode": result.mode, "confidence": round(result.confidence, 4),
                "citations": citations, "rewritten_used": rw.rewritten_used,
            })

            system, user_prompt, max_tokens = build_qa_prompt(
                blocks, history, message, result.mode,
                max_tokens=settings.rag_llm_max_tokens,
                conservative_tokens=settings.rag_llm_conservative_tokens,
            )

            parts: list[str] = []
            ping_sec = settings.rag_stream_ping_sec
            try:
                async with _LLM_SEMAPHORE:
                    stream = chat_stream(
                        system, user_prompt, temperature=0.1, max_tokens=max_tokens
                    )
                    while True:
                        try:
                            # 单块等待加超时：LLM 静默超过 ping 阈值时先发 ping 保活（RAG 契约 §0.2/§3.7）
                            delta = await asyncio.wait_for(anext(stream), timeout=ping_sec)
                        except asyncio.TimeoutError:
                            yield _sse("ping", {"type": "ping"})
                            continue
                        except StopAsyncIteration:
                            break
                        # 输出流式敏感词复检（RAG 方案 §3.8）：命中片替换为屏蔽标记并终止
                        hits = contains_sensitive(delta)
                        if hits:
                            yield _sse("delta", {"text": "［内容已屏蔽］"})
                            logger.warning("输出敏感词拦截：%s", "、".join(hits))
                            break
                        yield _sse("delta", {"text": delta})
                        parts.append(delta)
            except (GeneratorExit, asyncio.CancelledError):
                # 客户端断连：best-effort 落 INTERRUPTED 部分文本，再关闭
                partial = "".join(parts)
                try:
                    QaService._persist_assistant(
                        db, conv, user_msg_id, partial or "（回答中断）", blocks,
                        grounding=0.0, status=MessageStatus.INTERRUPTED,
                    )
                    ConversationRepo.touch(db, conv)
                except Exception:  # noqa: BLE001
                    logger.exception("断线消息落库失败")
                raise
            except LLMError as exc:
                logger.error("LLM 流失败：%s", exc)
                try:
                    QaService._persist_assistant(
                        db, conv, user_msg_id, "（回答生成失败，请重试）", blocks,
                        grounding=0.0, status=MessageStatus.FAILED,
                    )
                    ConversationRepo.touch(db, conv)
                except Exception:  # noqa: BLE001
                    logger.exception("失败消息落库失败")
                yield _sse("done", {
                    "answer_id": 0, "citations": citations,
                    "grounding_score": 0.0, "synthetic": True,
                    "error": "回答生成失败，请重试",
                })
                return

            # grounding 校验：越界 [n] 删除，无脚注置 0（不重生成）
            text = "".join(parts).strip()
            text, grounded, total, grounding_score = _ground(text, len(citations))

            # assistant + message_source 单事务落库 → touch → done
            answer_id = QaService._persist_assistant(
                db, conv, user_msg_id, text, blocks,
                grounding=grounding_score, status=MessageStatus.SUCCESS,
            )
            ConversationRepo.touch(db, conv)
            yield _sse("done", {
                "answer_id": answer_id, "citations": citations,
                "grounding_score": grounding_score, "synthetic": True,
            })

    # ---------- 落库 ----------

    @staticmethod
    def _persist_assistant(
        db, conv, user_msg_id: int, text: str, blocks: list[RetrievedBlock],
        *, grounding: float, status: str,
    ) -> int:
        """assistant 消息 + message_source 单事务落库，返回 assistant 消息 id。

        source 的 document_id/chunk_id 来自 Chroma metadata 里回填的 db 自增 int
        （G3：message_source 可 join 回 knowledge_document/knowledge_chunk）。
        score 存「展示相关度」（display_score 相对理论峰值归一化；展开块存下限 0.05），
        与 live to_source 同口径，历史消息相关度条不再 1%-3%。
        """
        rrf_k = RAGParams.from_settings().rrf_k
        msg = MessageRepo.create(
            db, commit=False,
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content=text,
            token_count=_estimate_tokens(text),
            status=status,
        )
        sources = []
        for b in blocks:
            if not b.db_doc_id or not b.db_chunk_id:
                continue
            sources.append({
                "message_id": msg.id,
                "document_id": b.db_doc_id,
                "chunk_id": b.db_chunk_id,
                "doc_id": b.doc_id or None,
                "article_no": b.article_no or None,
                "document_name": b.title or "",
                "chapter": b.chapter or None,
                "content": (b.content or "")[:500],
                "score": _to_score(display_score(b.rrf_score, rrf_k)),
            })
        if sources:
            MessageSourceRepo.create_many(db, sources)
        db.commit()
        logger.info("问答落库 conv=%s user=%s assistant=%s sources=%d grounding=%.3f",
                    conv.id, user_msg_id, msg.id, len(sources), grounding)
        return msg.id


def _to_score(rrf: float) -> Decimal | None:
    if not rrf or rrf <= 0:
        return None
    return Decimal(str(round(rrf, 4)))


def _ground(text: str, n_citations: int) -> tuple[str, int, int, float]:
    """grounding 校验：删除越界 [n]，返回 (清洗后文本, 有效引用数, 引用总数, 得分)。

    - 有引用：得分 = 有效数 / 总数（越界引用说明模型幻觉，扣分但不重生成）；
    - 无引用：得分 0（文本不带脚注，按契约不强制重生成）。
    """
    if not text:
        return text, 0, 0, 0.0
    valid = 0
    total = 0
    out_of_range: list[tuple[int, int]] = []  # (start, end)
    for m in _REF_RE.finditer(text):
        total += 1
        n = int(m.group(1))
        if 1 <= n <= n_citations:
            valid += 1
        else:
            out_of_range.append((m.start(), m.end()))
    if total == 0:
        return text, 0, 0, 0.0
    for start, end in reversed(out_of_range):
        text = text[:start] + text[end:]
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text, valid, total, round(valid / total, 4)
