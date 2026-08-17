"""模块二 AI 智能助手 ORM 模型（对应 schema.sql 的 5 张 AI 表）。

会话 / 消息 / 回答引用 / 知识库文档 / 知识切片。全部逻辑外键（无物理外键），
风格照 model/question.py：Mapped + BigInteger + func.now() 时间戳 + 模块级常量类。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric, String, Text, func, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class MessageRole:
    USER = "user"            # 用户提问
    ASSISTANT = "assistant"  # AI 回答


class MessageStatus:
    SUCCESS = "SUCCESS"          # 生成完成
    FAILED = "FAILED"            # 生成失败/中断（可重试）
    INTERRUPTED = "INTERRUPTED"  # 客户端断连


class KnowledgeDocumentStatus:
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(mysql.MEDIUMTEXT, nullable=False)
    token_count: Mapped[int] = mapped_column(
        mysql.INTEGER, default=0, server_default=text("0"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default=MessageStatus.SUCCESS, server_default=text("'SUCCESS'"), nullable=False
    )
    # feedback 由 M4 迁移（_migrate_ai_chat 幂等 ALTER）加列：NULL=未反馈、1=有用、-1=没用、0=清除
    feedback: Mapped[int | None] = mapped_column(mysql.TINYINT)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MessageSource(Base):
    __tablename__ = "message_source"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    # document_id / chunk_id 是 BIGINT 逻辑外键，指向 knowledge_document.id / knowledge_chunk.id
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # doc_id/article_no 是检索层原文定位（get_article 查回父块用），历史引用可点击查看原文
    doc_id: Mapped[str | None] = mapped_column(String(64))
    article_no: Mapped[str | None] = mapped_column(String(64))
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    chapter: Mapped[str | None] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # category：法律/行政法规/部门规章/政府规章/地方性法规
    # O10 文档库扩展列（幂等迁移 _migrate_knowledge_document_meta 补齐；老数据从 crawler_output 回填）
    doc_type: Mapped[str | None] = mapped_column(String(16))       # law/regulation/company/sop/plan/case
    doc_level: Mapped[int | None] = mapped_column(mysql.INTEGER)   # 行政层级：1 法律 2 行政法规 3 部门规章 …
    region: Mapped[str | None] = mapped_column(String(64))         # 区域：四川/国家/…
    source_url: Mapped[str | None] = mapped_column(String(512))    # 来源链接
    path: Mapped[str] = mapped_column(String(255), nullable=False)  # 源文件名
    status: Mapped[str] = mapped_column(
        String(16), default=KnowledgeDocumentStatus.PENDING,
        server_default=text("'PENDING'"), index=True, nullable=False
    )
    chunk_count: Mapped[int] = mapped_column(
        mysql.INTEGER, default=0, server_default=text("0"), nullable=False
    )
    uploader_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunk"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chapter: Mapped[str | None] = mapped_column(String(128))
    page_no: Mapped[int | None] = mapped_column(mysql.INTEGER)
    seq: Mapped[int] = mapped_column(mysql.INTEGER, nullable=False)
    vector_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # = Chroma chunk_id
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
