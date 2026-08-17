"""模块一 隐患安全管理请求/响应 Schema（照 schema/question.py 风格）。

输出响应统一由 service 层手写 dict（对齐考试工坊 _to_dict 模式，因详情要 join 图片/时间线），
本文件只放输入模型与枚举别名；Level 用 Literal 约束取值（对齐 DATABASE.md §4.1）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 隐患等级（hazard.level，DATABASE.md §4.1）
HazardLevelLiteral = Literal["CRITICAL", "MAJOR", "GENERAL", "MINOR"]


class HazardCreate(BaseModel):
    """H01 隐患上报请求体。

    必填：description（描述）、level（等级）——对齐 PRD H01 验收「必填项校验（描述、等级）」。
    title 缺省自动取 description 前 20 字；location 缺省落「未填写」（DDL NOT NULL 约束）；
    type 缺省「其他」；images 是已上传图片的 URL 列表（先调 POST /upload 拿 url 再随表单提交）。
    reporter_name 为现场上报人姓名（缺省取当前登录用户姓名，前端可填他人代报）。
    risk_report 为 AI 识别结果（前端勾选保留后回传；kept=false 表示未保留识别，详情仅原图）。
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=128)
    description: str = Field(min_length=1, max_length=2000)
    location: str | None = Field(default=None, max_length=128)
    level: HazardLevelLiteral
    type: str = Field(default="其他", max_length=32)
    reporter_name: str | None = Field(default=None, max_length=64)  # 现场上报人（缺省=当前用户姓名）
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


class HazardDispatchIn(BaseModel):
    """H04 派单请求体：指定整改负责人与整改期限。

    handler_id 必须存在（service 校验用户存在且启用）；deadline 可选（未填则不设整改期限）。
    """

    model_config = ConfigDict(extra="forbid")

    handler_id: int = Field(ge=1)
    deadline: datetime | None = Field(default=None)


class HazardRectifyIn(BaseModel):
    """H05 整改反馈请求体：整改措施必填，整改后照片 URL 可选（≤9 张）。"""

    model_config = ConfigDict(extra="forbid")

    rectification_measure: str = Field(min_length=1, max_length=2000)
    rectification_images: list[str] = Field(default_factory=list, max_length=9)


class HazardCheckIn(BaseModel):
    """H06 验收请求体：通过（FINISHED）或驳回（REJECTED，必须填写原因）。

    passed=True 验收通过闭环；passed=False 需填 reject_reason（400 拦截无原因驳回）。
    """

    model_config = ConfigDict(extra="forbid")

    passed: bool
    reject_reason: str | None = Field(default=None, max_length=255)


class HazardAuditIn(BaseModel):
    """O13 安全员隐患处理请求体（模拟实现）：标记已处理/驳回 + 处理意见。

    passed=True 标记已处理；passed=False 需填 comment（400 拦截无意见驳回）。
    """

    model_config = ConfigDict(extra="forbid")

    passed: bool
    comment: str | None = Field(default=None, max_length=255)
