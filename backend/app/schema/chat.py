"""AI 智能助手（模块二）Pydantic 模型。

请求模型（ChatIn/ConversationUpdate/FeedbackIn）供 api 层校验入参；
响应模型（QuickQuestion/ArticleOut）供 chat_service 组装返回 data。
约定：统一响应 {code, message, data}（app.utils.response.resp）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    """发送一条问题（A01 智能问答）。

    - conversation_id 为空 → 新建会话（首问自动生成标题）；
    - message 长度 1..2000（过长提示拆分）；敏感词由服务层预检。
    """

    conversation_id: int | None = Field(default=None)
    message: str = Field(min_length=1, max_length=2000)
    # 保留 mode 扩展位（如 strict/precise），MVP 恒 None（走默认检索链路）
    mode: str | None = Field(default=None, max_length=16)
    # O11 文件上传：解析后的文档文本（会话级临时上下文，≤8000 字，仅当前会话）
    file_context: str | None = Field(default=None, max_length=8000)


class ConversationUpdate(BaseModel):
    """会话重命名（A02 会话管理）。"""

    title: str = Field(min_length=1, max_length=64)


class FeedbackIn(BaseModel):
    """回答反馈（A07 点赞/点踩）。

    value 语义：1=有用、-1=没用、0=清除反馈；单行 UPDATE 幂等。
    """

    value: Literal[-1, 0, 1]


class QuickQuestion(BaseModel):
    """快捷提问项（A04），按类目分组展示。"""

    category: str
    question: str


class ArticleOut(BaseModel):
    """查看原文（A03 RAG 检索溯源）：父块全文 + 出处字段。"""

    doc_id: str
    title: str
    doc_no: str
    category: str
    doc_level: int
    region: str
    chapter: str
    article_no: str
    content: str
    status: str
    publish_date: str
    effective_date: str
    version: str
    source_url: str
