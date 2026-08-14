"""AI 智能助手（模块二）业务层：会话 / 消息 / 回答引用 / 快捷提问 / 查看原文。

风格照 exam_service.py：静态方法 + Session 首参 + HTTPException；
归属校验统一 404 掩码（不存在 / 非本人 同文案，防会话 ID 枚举，对齐 #14 惯例）。
"""
from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, status

from ..core.config import get_settings
from ..model.chat import Conversation, Message, MessageSource
from ..repository.chat_repo import (
    ConversationRepo,
    MessageRepo,
    MessageSourceRepo,
)
from ..schema.chat import ArticleOut, QuickQuestion
from ..rag.retriever import ACCESS_EMPLOYEE, get_retriever

# backend/data/quick_questions.json：config.py 位于 backend/app/core，父级两级 = backend
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_QUICK_FILE = _DATA_DIR / "quick_questions.json"


@lru_cache(maxsize=1)
def load_quick_questions() -> list[dict]:
    """快捷提问（A04）：JSON 按类目分组，启动预热一次，不进 DB。"""
    if not _QUICK_FILE.exists():
        return []
    try:
        data = json.loads(_QUICK_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data.get("questions", []) if isinstance(data, dict) else []


class ChatService:
    # ---------- 会话管理（A02） ----------

    @staticmethod
    def create_conversation(db, user, title: str) -> dict:
        """建会话；title 空则默认「新会话」（首问时由 qa_service 再自动重命名为提问）。"""
        conv = ConversationRepo.create(db, user_id=user.id, title=title or "新会话")
        return ChatService._conv_out(conv)

    @staticmethod
    def list_conversations(db, user, *, page: int = 1, page_size: int = 20) -> dict:
        items = ConversationRepo.list_by_user(db, user.id, page=page, page_size=page_size)
        return {
            "total": ConversationRepo.count_by_user(db, user.id),
            "items": [ChatService._conv_out(c) for c in items],
        }

    @staticmethod
    def rename_conversation(db, user, cid: int, title: str) -> dict:
        conv = ChatService._get_owned(db, cid, user)
        return ChatService._conv_out(ConversationRepo.rename(db, conv, title))

    @staticmethod
    def delete_conversation(db, user, cid: int) -> None:
        conv = ChatService._get_owned(db, cid, user)
        ConversationRepo.delete_cascade(db, conv)

    # ---------- 消息 / 引用 ----------

    @staticmethod
    def list_messages(db, user, cid: int) -> list[dict]:
        """会话内消息列表；assistant 消息内联 sources 引用卡片（meta 快照同源）。"""
        ChatService._get_owned(db, cid, user)
        out = []
        for m in MessageRepo.list_by_conversation(db, cid):
            item = {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "token_count": m.token_count,
                "status": m.status,
                "feedback": m.feedback if m.feedback is not None else 0,
                "create_time": m.create_time.isoformat() if m.create_time else None,
                "sources": [],
            }
            if m.role == "assistant" and m.status == "SUCCESS":
                for s in MessageSourceRepo.list_by_message(db, m.id):
                    item["sources"].append({
                        "document_id": s.document_id,
                        "chunk_id": s.chunk_id,
                        "doc_id": s.doc_id,
                        "article_no": s.article_no,
                        "document_name": s.document_name,
                        "chapter": s.chapter,
                        "content": s.content,
                        "score": float(s.score) if s.score is not None else None,
                    })
            out.append(item)
        return out

    @staticmethod
    def get_sources(db, user, message_id: int) -> list[dict]:
        """回答引用列表（A03）；非本人消息统一 404 掩码。"""
        msg = ChatService._get_message_owned(db, user, message_id)
        if msg.role != "assistant":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="该消息不是 AI 回答")
        return [
            {
                "document_id": s.document_id,
                "chunk_id": s.chunk_id,
                "doc_id": s.doc_id,
                "article_no": s.article_no,
                "document_name": s.document_name,
                "chapter": s.chapter,
                "content": s.content,
                "score": float(s.score) if s.score is not None else None,
            }
            for s in MessageSourceRepo.list_by_message(db, message_id)
        ]

    # ---------- 反馈（A07） ----------

    @staticmethod
    def set_feedback(db, user, message_id: int, value: int) -> None:
        msg = ChatService._get_message_owned(db, user, message_id)
        if msg.role != "assistant":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="只能给 AI 回答反馈")
        MessageRepo.set_feedback(db, message_id, value)

    # ---------- 快捷提问 / 查看原文 ----------

    @staticmethod
    def quick_questions() -> list[QuickQuestion]:
        return [QuickQuestion(**q) for q in load_quick_questions()]

    @staticmethod
    def get_article(db, user, doc_id: str, article_no: str) -> ArticleOut:
        """查看原文（A03）：走检索层父块索引（无需 DB 会话归属）。"""
        block = get_retriever().get_article(doc_id, article_no, access_levels=ACCESS_EMPLOYEE)
        if block is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="未找到对应条文")
        return ArticleOut(
            doc_id=block.doc_id,
            title=block.title,
            doc_no=block.doc_no,
            category=block.category,
            doc_level=block.doc_level,
            region=block.region,
            chapter=block.chapter,
            article_no=block.article_no,
            content=block.content,
            status=block.status,
            publish_date=block.publish_date,
            effective_date=block.effective_date,
            version=block.version,
            source_url=block.source_url,
        )

    # ---------- 内部工具 ----------

    @staticmethod
    def _get_owned(db, cid: int, user) -> Conversation:
        conv = ConversationRepo.get_by_id(db, cid)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="会话不存在")
        return conv

    @staticmethod
    def _get_message_owned(db, user, message_id: int) -> Message:
        msg = MessageRepo.get_by_id(db, message_id)
        if msg is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="消息不存在")
        conv = ConversationRepo.get_by_id(db, msg.conversation_id)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="消息不存在")
        return msg

    @staticmethod
    def _conv_out(c: Conversation) -> dict:
        return {
            "id": c.id,
            "title": c.title,
            "created_time": c.created_time.isoformat() if c.created_time else None,
            "updated_time": c.updated_time.isoformat() if c.updated_time else None,
        }
