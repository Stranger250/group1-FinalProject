"""AI 出题（E02）相关 Pydantic 模型。

请求模型（GenRequest/ReviewIn/BatchReviewIn）供 api 层校验入参；
输出模型（SourceItem/GenQuestion/GenOutput）供 gen_service 解析 LLM 返回 JSON，
采用宽松校验（extra="ignore"），容忍模型输出多余字段。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AiQuestionType = Literal["SINGLE", "MULTIPLE", "JUDGE", "FILL"]
AiQuestionDifficulty = Literal["EASY", "MEDIUM", "HARD"]
AiReviewAction = Literal["APPROVE", "REJECT"]


class GenRequest(BaseModel):
    """AI 出题请求。

    技术决策：入库状态机（DATABASE.md §6.1）——生成仅入草稿（source=ai, status=PENDING），
    审核通过才 APPROVED。
    """

    knowledge_point: str = Field(min_length=1, max_length=64)
    types: list[AiQuestionType] = Field(min_length=1)  # 元素枚举 SINGLE/MULTIPLE/JUDGE/FILL，至少一种题型
    difficulty: AiQuestionDifficulty  # EASY/MEDIUM/HARD
    count: int = Field(ge=1, le=20)
    law_title: str | None = Field(default=None, max_length=128)

    @field_validator("count")
    @classmethod
    def _count_at_least_five(cls, v: int) -> int:
        if v < 5:
            raise ValueError("每次生成不少于 5 题（PRD E02 验收）")
        return v


class SourceItem(BaseModel):
    """LLM 输出 sources 列表元素（溯源）。

    role 取值：answer=正确答案来源、distractor=干扰项来源、analysis=解析来源。
    """

    model_config = ConfigDict(extra="ignore")

    role: str
    law_title: str | None = None
    article_no: str | None = None


class GenQuestion(BaseModel):
    """LLM 单题输出，宽松校验（容忍多余字段，不强制 sources 齐全）。"""

    model_config = ConfigDict(extra="ignore")

    type: str
    content: str
    options: list[str] | None = None
    answer: str
    analysis: str | None = None
    knowledge_point: str
    difficulty: str
    source_law_title: str | None = None
    source_article_no: str | None = None
    sources: list[SourceItem] | None = None


class GenOutput(BaseModel):
    """LLM 整体输出。"""

    model_config = ConfigDict(extra="ignore")

    questions: list[GenQuestion]


class ReviewIn(BaseModel):
    """单题审核入参（入库状态机：APPROVED/REJECTED）。"""

    action: AiReviewAction
    review_note: str | None = Field(default=None, max_length=255)
    interference_verified: bool = False


class BatchReviewIn(BaseModel):
    """整批/部分审核入参；ids 为空则整批（按 batch_id）。"""

    action: AiReviewAction
    review_note: str | None = Field(default=None, max_length=255)
    interference_verified: bool = False
    ids: list[int] | None = None  # 为空则整批


class RewriteIn(BaseModel):
    """AI 重写入参（E02 增强，方案B）。

    仅可重写已驳回（REJECTED）的 AI 生成题：把驳回意见 + 本次修订要求 + 相关条款
    回喂 LLM，产出修订版新题（source=ai、status=PENDING、rewrite_of=原题 id）。
    """

    feedback: str = Field(min_length=1, max_length=255, description="本次修订要求（如：把选项B改成与条款一致）")
