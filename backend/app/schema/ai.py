"""AI 出题（E02）相关 Pydantic 模型。

请求模型（GenRequest/ReviewIn/BatchReviewIn）供 api 层校验入参；
输出模型（SourceItem/GenQuestion/GenOutput）供 gen_service 解析 LLM 返回 JSON，
采用宽松校验（extra="ignore"），容忍模型输出多余字段。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.config import get_settings

AiQuestionType = Literal["SINGLE", "MULTIPLE", "JUDGE", "FILL", "SUBJECTIVE"]
AiQuestionDifficulty = Literal["EASY", "MEDIUM", "HARD"]
AiReviewAction = Literal["APPROVE", "REJECT"]


class GenRequest(BaseModel):
    """AI 出题请求。

    技术决策：入库状态机（DATABASE.md §6.1）——生成仅入草稿（source=ai, status=PENDING），
    审核通过才 APPROVED。
    提供 reference_text 时 knowledge_point 可空，以文档限定出题范围（E02 上传参考文档）。
    """

    knowledge_point: str | None = Field(default=None, min_length=1, max_length=64)
    types: list[AiQuestionType] = Field(min_length=1)  # 元素枚举 SINGLE/MULTIPLE/JUDGE/FILL，至少一种题型
    difficulty: AiQuestionDifficulty  # EASY/MEDIUM/HARD
    count: int = Field(ge=1)  # 上下限由 _count_bounds 依据 settings.gen_min_count / gen_max_count 校验（单一真源）
    law_title: str | None = Field(default=None, max_length=128)
    # 上传参考文档（/doc 端点解析出的纯文本，最外层经 ref_doc_max_chars 截断）
    reference_text: str | None = Field(default=None, max_length=6000)
    # 上传参考文档文件名（溯源显示名）
    reference_title: str | None = Field(default=None, max_length=128)

    @field_validator("count")
    @classmethod
    def _count_bounds(cls, v: int) -> int:
        s = get_settings()
        if v < s.gen_min_count:
            raise ValueError(f"每次生成不少于 {s.gen_min_count} 题（PRD E02 验收）")
        if v > s.gen_max_count:
            raise ValueError(f"每次生成不超过 {s.gen_max_count} 题（超出上限请分批生成）")
        return v


class RefDocOut(BaseModel):
    """参考文档解析结果（/doc 端点回传，纯文本由前端再回传 /generate 限定出题范围）。

    truncated=True 表示文本超出 ref_doc_max_chars 已被截断；text 为截断后的纯文本。
    """

    filename: str
    size: int
    chars: int
    truncated: bool
    text: str


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
