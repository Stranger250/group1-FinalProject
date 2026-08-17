"""模块一 隐患安全管理 ORM 模型（对应 schema.sql 的 3 张隐患表，对齐 DATABASE.md §4）。

hazard 隐患主表 / hazard_image 隐患图片 / hazard_log 处理留痕（H03 时间线）。
全部逻辑外键（无物理外键），风格照 model/chat.py：Mapped + BigInteger + func.now() + 模块级常量类。

本期范围 H01–H03：状态只流转 WAIT_PROCESS → FINISHED（PRD 简化闭环）；
PROCESSING/WAIT_CHECK/REJECTED 及 handler_id/deadline/rectification_* 是 H04–H06 预留字段，本期不写。
risk_report（JSON）为 H01 AI 图片识别报告预留，本期由视觉模型写入。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class HazardStatus:
    """隐患状态（hazard.status，DATABASE.md §4.1）。"""

    WAIT_PROCESS = "WAIT_PROCESS"  # 待处理（提交后初始态）
    PROCESSING = "PROCESSING"      # 处理中（H04 派单后，本期预留）
    WAIT_CHECK = "WAIT_CHECK"      # 待验收（H05 整改后，本期预留）
    FINISHED = "FINISHED"          # 已闭环
    REJECTED = "REJECTED"          # 已驳回（本期预留）


class HazardLevel:
    """隐患等级（hazard.level，DATABASE.md §4.1）。"""

    CRITICAL = "CRITICAL"  # 重大：可能导致重大安全事故，需立即整改
    MAJOR = "MAJOR"        # 较大：可能导致较大安全事故，限期整改
    GENERAL = "GENERAL"    # 一般：一般性问题，常规整改
    MINOR = "MINOR"        # 轻微：轻微问题，建议整改


class HazardType:
    """隐患类型（hazard.type，DATABASE.md §4.1：按企业分类维护，示例清单）。"""

    HIGH_ALTITUDE = "高处作业"
    ELECTRICAL = "用电安全"
    MECHANICAL = "机械伤害"
    FIRE = "消防"
    EDGE = "临边防护"
    OTHER = "其他"


class HazardAuditStatus:
    """隐患处理状态（hazard.audit_status，PRD-V2 O13：安全员隐患处理，模拟实现）。"""

    PENDING = "pending"      # 待处理（上报后初始态）
    APPROVED = "approved"    # 已处理
    REJECTED = "rejected"    # 已驳回


class HazardLogOperation:
    """处理留痕操作（hazard_log.operation，DATABASE.md §4.4：提交/派单/整改/验收/驳回）。"""

    SUBMIT = "提交"
    DISPATCH = "派单"
    RECTIFY = "整改"
    ACCEPT = "验收"
    REJECT = "驳回"
    CLOSE = "闭环"


class Hazard(Base):
    __tablename__ = "hazard"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hazard_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # 唯一编号，提交时生成
    title: Mapped[str] = mapped_column(String(128), nullable=False)  # 自动取描述前 20 字
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(String(128), nullable=False)  # 可空上报 → 默认「未填写」
    level: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=HazardStatus.WAIT_PROCESS,
        server_default=text("'WAIT_PROCESS'"), index=True, nullable=False,
    )
    creator_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)  # 上报人 → user.id
    reporter_name: Mapped[str | None] = mapped_column(String(64))  # 现场上报人姓名（缺省=登录用户姓名，可代报）
    handler_id: Mapped[int | None] = mapped_column(BigInteger, index=True)  # 整改负责人（H04 预留）
    deadline: Mapped[datetime | None] = mapped_column(DateTime)  # 整改期限（H04 预留）
    rectification_measure: Mapped[str | None] = mapped_column(Text)  # 整改措施（H05 预留）
    rectification_images: Mapped[str | None] = mapped_column(Text)  # 整改后照片 URL（H05 预留）
    reject_reason: Mapped[str | None] = mapped_column(String(255))  # 驳回原因（H06 预留）
    risk_report: Mapped[dict | None] = mapped_column(JSON)  # AI 图片识别报告（标签/置信度/建议）
    # O13 安全员隐患处理（模拟实现）：处理状态/处理人/处理时间/处理意见
    audit_status: Mapped[str] = mapped_column(
        String(16), default=HazardAuditStatus.PENDING,
        server_default=text("'pending'"), index=True, nullable=False,
    )
    audit_by: Mapped[int | None] = mapped_column(BigInteger)  # 处理人 user.id
    audit_at: Mapped[datetime | None] = mapped_column(DateTime)  # 处理时间
    audit_comment: Mapped[str | None] = mapped_column(String(255))  # 处理意见
    subcategory: Mapped[str | None] = mapped_column(String(64))  # O1 子类名称（大类 type 下细分）
    create_time: Mapped[datetime] = mapped_column(DateTime, index=True, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class HazardImage(Base):
    __tablename__ = "hazard_image"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hazard_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    image_url: Mapped[str] = mapped_column(String(255), nullable=False)  # /uploads/... 相对路径
    uploader_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HazardLog(Base):
    __tablename__ = "hazard_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hazard_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    operator_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)  # 提交/闭环（本期）
    old_status: Mapped[str | None] = mapped_column(String(16))
    new_status: Mapped[str | None] = mapped_column(String(16))
    remark: Mapped[str | None] = mapped_column(String(255))
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HazardCategory(Base):
    """O1 隐患分类（三级体系：大类 parent_id=0 → 子类）。"""

    __tablename__ = "hazard_category"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    check_items: Mapped[str | None] = mapped_column(String(255))  # 检查项说明
    enabled: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)  # 1=启用 0=停用
    sort_order: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
