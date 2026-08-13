"""AI 智能助手（模块二）数据访问：会话 / 消息 / 回答引用 / 知识库。

风格照 question_repo.py：commit-per-method；MessageRepo.create 支持
commit=False + flush 拿 id（SSE 流中先落 user 行再 COMMIT，断线不丢历史）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..model.chat import Conversation, Message, MessageSource


class ConversationRepo:
    @staticmethod
    def get_by_id(db: Session, cid: int) -> Conversation | None:
        return db.get(Conversation, cid)

    @staticmethod
    def list_by_user(db: Session, user_id: int, *, page: int = 1, page_size: int = 20) -> list[Conversation]:
        return list(
            db.scalars(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_time.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )

    @staticmethod
    def count_by_user(db: Session, user_id: int) -> int:
        return db.scalar(select(func.count(Conversation.id)).where(Conversation.user_id == user_id)) or 0

    @staticmethod
    def create(db: Session, *, user_id: int, title: str) -> Conversation:
        c = Conversation(user_id=user_id, title=title)
        db.add(c)
        db.commit()
        db.refresh(c)
        return c

    @staticmethod
    def rename(db: Session, conversation: Conversation, title: str) -> Conversation:
        conversation.title = title
        conversation.updated_time = datetime.now()
        db.commit()
        db.refresh(conversation)
        return conversation

    @staticmethod
    def touch(db: Session, conversation: Conversation) -> None:
        """会话 updated_time 刷新（每条消息落库后调用，会话列表按此排序）。"""
        conversation.updated_time = datetime.now()
        db.commit()

    @staticmethod
    def delete_cascade(db: Session, conversation: Conversation) -> None:
        """单事务三级删：message_source → message → conversation（A02 删除会话）。"""
        message_ids = db.scalars(
            select(Message.id).where(Message.conversation_id == conversation.id)
        ).all()
        if message_ids:
            db.execute(delete(MessageSource).where(MessageSource.message_id.in_(message_ids)))
            db.execute(delete(Message).where(Message.id.in_(message_ids)))
        db.delete(conversation)
        db.commit()


class MessageRepo:
    @staticmethod
    def get_by_id(db: Session, mid: int) -> Message | None:
        return db.get(Message, mid)

    @staticmethod
    def create(db: Session, *, commit: bool = True, **kwargs) -> Message:
        """落一条消息；commit=False 时调用方在 flush 后自行 commit（SSE 流内先落 user 行）。"""
        m = Message(**kwargs)
        db.add(m)
        db.flush()
        if commit:
            db.commit()
            db.refresh(m)
        return m

    @staticmethod
    def update_status(db: Session, mid: int, status: str) -> None:
        db.execute(update(Message).where(Message.id == mid).values(status=status))
        db.commit()

    @staticmethod
    def list_by_conversation(db: Session, conversation_id: int) -> list[Message]:
        """会话内全部消息（时间正序，首答 user 行已在先）。"""
        return list(
            db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.id)
            )
        )

    @staticmethod
    def list_history_questions(db: Session, conversation_id: int, *, limit: int = 5) -> list[str]:
        """最近 limit 条 user 问句（时间正序，供规则多轮改写）。"""
        rows = db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.role == "user")
            .order_by(Message.id.desc())
            .limit(limit)
        ).all()
        return [m.content for m in reversed(rows)]

    @staticmethod
    def count(db: Session, conversation_id: int) -> int:
        return db.scalar(
            select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        ) or 0

    @staticmethod
    def set_feedback(db: Session, mid: int, value: int) -> None:
        """单行 UPDATE 幂等；value=0 清除反馈。归属校验在 service 层。"""
        db.execute(update(Message).where(Message.id == mid).values(feedback=value))
        db.commit()


class MessageSourceRepo:
    @staticmethod
    def create_many(db: Session, items: list[dict]) -> list[MessageSource]:
        """回答引用批量落库（与 assistant 消息同一事务）。"""
        rows = [MessageSource(**it) for it in items]
        db.add_all(rows)
        db.flush()
        return rows

    @staticmethod
    def list_by_message(db: Session, message_id: int) -> list[MessageSource]:
        return list(
            db.scalars(
                select(MessageSource)
                .where(MessageSource.message_id == message_id)
                .order_by(MessageSource.id)
            )
        )
