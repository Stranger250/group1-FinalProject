"""在线考试（E04/E05）相关 Pydantic 模型。

对齐 PRD E04/E05 验收：
- 开始考试（指定 PUBLISHED 试卷）→ 进行中记录 + 脱敏题目 + 倒计时；
- save/submit 均传增量答案（重复 question_id 去重取最后值）；
- switch 上报前端切屏累计计数（服务端以 max 合并，权威在服务端）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ExamStartIn(BaseModel):
    paper_id: int = Field(ge=1)


class AnswerItem(BaseModel):
    question_id: int = Field(ge=1)
    user_answer: str = Field(default="", max_length=255)  # 放宽至 255 适配填空多空中文答案


class ExamAnswersIn(BaseModel):
    """save / submit 共用：增量答案列表；重复 question_id 去重取最后值。"""

    answers: list[AnswerItem] = Field(default_factory=list, max_length=500)

    @field_validator("answers")
    @classmethod
    def _dedup(cls, v: list[AnswerItem]) -> list[AnswerItem]:
        seen: dict[int, AnswerItem] = {}
        for item in v:
            seen[item.question_id] = item  # 后者覆盖前者
        return list(seen.values())


class ExamSwitchIn(BaseModel):
    """切屏上报：前端累计计数（可从 0 起步逐步上报）。"""

    cheat_count: int = Field(ge=0, le=100000)
