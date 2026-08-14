"""模块一 隐患安全管理请求/响应 Schema（照 schema/question.py 风格）。

输出响应统一由 service 层手写 dict（对齐考试工坊 _to_dict 模式，因详情要 join 图片/时间线），
本文件只放输入模型与枚举别名；Level 用 Literal 约束取值（对齐 DATABASE.md §4.1）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 隐患等级（hazard.level，DATABASE.md §4.1）
HazardLevelLiteral = Literal["CRITICAL", "MAJOR", "GENERAL", "MINOR"]


class HazardCreate(BaseModel):
    """H01 隐患上报请求体。

    必填：description（描述）、level（等级）——对齐 PRD H01 验收「必填项校验（描述、等级）」。
    title 缺省自动取 description 前 20 字；location 缺省落「未填写」（DDL NOT NULL 约束）；
    type 缺省「其他」；images 是已上传图片的 URL 列表（先调 POST /upload 拿 url 再随表单提交）。
    risk_report 为可选的 AI 识别结果（前端调用 /analyze 得到后回传，落 hazard.risk_report）。
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=128)
    description: str = Field(min_length=1, max_length=2000)
    location: str | None = Field(default=None, max_length=128)
    level: HazardLevelLiteral
    type: str = Field(default="其他", max_length=32)
    images: list[str] = Field(default_factory=list, max_length=9)  # 单隐患最多 9 张
    risk_report: dict | None = None


class VisionResult(BaseModel):
    """POST /hazards/analyze 的识别结果（视觉模型输出，前端回显供用户确认）。"""

    model_config = ConfigDict(extra="ignore")

    type_suggest: str = Field(default="其他", max_length=32)   # 建议隐患类型（中文候选）
    level_suggest: HazardLevelLiteral = "GENERAL"              # 建议隐患等级
    description: str = Field(default="", max_length=2000)      # 图片内容描述
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)     # 模型置信度
    report: dict = Field(default_factory=dict)                 # 原始识别报告（透传落库）
