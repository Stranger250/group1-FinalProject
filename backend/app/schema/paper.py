"""试卷生成（E03）相关 Pydantic 模型。

对齐 PRD E03 验收：
- 手动组卷：从题库勾选题目组成试卷；
- AI 智能组卷：指定题型数量/知识点/难度分布，自动从题库抽题，不足时给出提示；
- 试卷可配置考试时长（30/60/90 分钟）与合格线（默认 60 分）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PaperDuration = Literal[30, 60, 90]  # 考试时长（分钟），PRD E03 验收固定三档
PaperStatusType = Literal["DRAFT", "PUBLISHED", "DISABLED"]


def _check_pass_le_total(pass_score: int | None, total_score: int | None) -> None:
    """跨字段约束（#7）：及格线不得高于总分，否则考试永远无法通过。"""
    if pass_score is not None and total_score is not None and pass_score > total_score:
        raise ValueError("及格线不能高于总分")


class PaperQuestionIn(BaseModel):
    """手动组卷选中的题目；score 为空则整卷均分。"""

    question_id: int
    score: int | None = Field(default=None, ge=1, le=500)


class PaperManualCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    duration: PaperDuration
    pass_score: int = Field(default=60, ge=1, le=100)
    total_score: int = Field(default=100, ge=10, le=500)
    questions: list[PaperQuestionIn] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _pass_le_total(self):
        _check_pass_le_total(self.pass_score, self.total_score)
        return self


class PaperAutoRule(BaseModel):
    """AI 智能组卷规则：按「题型 × 难度」抽题数量；difficulty 缺省=全部难度。"""

    type: Literal["SINGLE", "MULTIPLE", "JUDGE", "FILL"]
    difficulty: Literal["EASY", "MEDIUM", "HARD"] | None = None
    count: int = Field(ge=1, le=100)


class PaperAutoCreate(BaseModel):
    """AI 智能组卷请求：rules 逐条抽题，knowledge_points 缺省=全部知识点。"""

    name: str = Field(min_length=1, max_length=128)
    duration: PaperDuration
    pass_score: int = Field(default=60, ge=1, le=100)
    total_score: int = Field(default=100, ge=10, le=500)
    rules: list[PaperAutoRule] = Field(min_length=1, max_length=50)
    knowledge_points: list[str] | None = None

    @field_validator("knowledge_points")
    @classmethod
    def _strip_kps(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned = [kp.strip() for kp in v if kp and kp.strip()]
        if not cleaned:
            raise ValueError("knowledge_points 不能为空")
        return cleaned

    @model_validator(mode="after")
    def _pass_le_total(self):
        _check_pass_le_total(self.pass_score, self.total_score)
        return self


class PaperUpdate(BaseModel):
    """更新试卷配置（草稿期可改；已发布仅可改名称/时长等，发布状态由 E04 管理）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    duration: PaperDuration | None = None
    pass_score: int | None = Field(default=None, ge=1, le=100)
    total_score: int | None = Field(default=None, ge=10, le=500)
    status: PaperStatusType | None = None

    @model_validator(mode="after")
    def _pass_le_total(self):
        _check_pass_le_total(self.pass_score, self.total_score)
        return self
