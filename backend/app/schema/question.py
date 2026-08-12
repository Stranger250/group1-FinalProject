"""题库（E01）相关 Pydantic 模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

QuestionType = Literal["SINGLE", "MULTIPLE", "JUDGE", "FILL"]
QuestionDifficulty = Literal["EASY", "MEDIUM", "HARD"]
QuestionStatus = Literal["PENDING", "APPROVED", "REJECTED", "DISABLED"]
QuestionSource = Literal["manual", "ai"]


class QuestionCreate(BaseModel):
    type: QuestionType
    content: str = Field(min_length=1)
    options: list[str] | None = None
    answer: str = Field(min_length=1, max_length=64)
    analysis: str = Field(min_length=1)  # PRD E01：正确答案与解析必填
    knowledge_point: str = Field(min_length=1, max_length=128)
    difficulty: QuestionDifficulty
    source_law_title: str | None = Field(default=None, max_length=255)
    source_article_no: str | None = Field(default=None, max_length=32)


class QuestionUpdate(BaseModel):
    type: QuestionType | None = None
    content: str | None = Field(default=None, min_length=1)
    options: list[str] | None = None
    answer: str | None = Field(default=None, min_length=1, max_length=64)
    analysis: str | None = Field(default=None, min_length=1)
    knowledge_point: str | None = Field(default=None, min_length=1, max_length=128)
    difficulty: QuestionDifficulty | None = None
    status: QuestionStatus | None = None
    review_note: str | None = Field(default=None, max_length=255)


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: str | None = None
    type: str
    content: str
    options: list[str] | None = None
    answer: str
    analysis: str | None = None
    knowledge_point: str
    difficulty: str
    source: str
    sources: list[dict[str, Any]] | None = None
    source_law_title: str | None = None
    source_article_no: str | None = None
    status: str
    reviewer: int | None = None
    review_note: str | None = None
    interference_verified: int = 0
    rewrite_of: int | None = None
    rewrite_feedback: str | None = None
    create_time: datetime
    update_time: datetime


class PageOut(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[QuestionOut]
