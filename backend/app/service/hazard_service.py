"""模块一 隐患安全管理业务编排（对应 DATABASE.md §4，对齐 PRD §3.2 H01–H03）。

- H01 create：单事务落「主表 + 图片行 + 时间线日志」；hazard_no = HZ+yyyyMMdd+4位序号，
  并发冲突（唯一键）回滚重试（最多 5 次）；
- H02 list_page：多条件筛选 + 分页（PRD 透明度设计：普通用户可见全部隐患）；
- H03 get：详情 + 图片 + 时间线（hazard_log 倒序）；
- close：管理员一键闭环 WAIT_PROCESS → FINISHED（角色门禁在 api 层，service 做纵深防御复检）。

风格照 service/exam_service.py：静态方法类 + 手写响应 dict + 404/400 HTTPException。
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..model.hazard import (
    Hazard,
    HazardImage,
    HazardLevel,
    HazardLogOperation,
    HazardStatus,
)
from ..model.user import RoleId, User
from ..repository.hazard_repo import HazardRepo
from ..schema.hazard import HazardCreate


def _now() -> datetime:
    """naive 本地时间，与 MySQL DATETIME 同口径（照 exam_service 约定）。"""
    return datetime.now()


logger = logging.getLogger("hazard_service")


class HazardService:
    # ---------- H01 上报 ----------

    @staticmethod
    def create(db: Session, payload: HazardCreate, user: User) -> dict:
        """H01 隐患上报：生成编号 → 单事务写主表/图片/时间线 → 返回完整详情。

        title 缺省自动取描述前 20 字（对齐会话标题模式）；location 缺省「未填写」；
        risk_report 透传视觉识别结果（落 hazard.risk_report JSON）。
        """
        settings = get_settings()
        title = (payload.title or "").strip() or HazardService._auto_title(payload.description)
        location = (payload.location or "").strip() or "未填写"
        hazard_type = (payload.type or "").strip() or "其他"
        description = payload.description.strip()

        # hazard_no 唯一键并发冲突 → 回滚重试（当日序号 +1）
        prefix = f"{settings.hazard_no_prefix}{_now().strftime('%Y%m%d')}"
        for attempt in range(5):
            seq = HazardRepo.count_by_no_prefix(db, prefix) + 1
            try:
                h = HazardRepo.create(
                    db, commit=False,
                    hazard_no=f"{prefix}-{seq:04d}",
                    title=title, description=description, location=location,
                    level=payload.level, type=hazard_type,
                    status=HazardStatus.WAIT_PROCESS,
                    creator_id=user.id, risk_report=payload.risk_report,
                )
                HazardRepo.add_images(db, h.id, payload.images, user.id, commit=False)
                HazardRepo.add_log(
                    db, h.id, user.id, HazardLogOperation.SUBMIT,
                    old_status=None, new_status=HazardStatus.WAIT_PROCESS,
                    remark="提交上报", commit=False,
                )
                db.commit()
                db.refresh(h)
                return HazardService._detail(db, h, user)
            except IntegrityError:
                # 并发同刻上报撞号：回滚本次插入，下一轮 count+1 重新生成
                db.rollback()
                if attempt == 4:
                    logger.exception("hazard_no 生成重试 5 次仍冲突")
                    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="编号生成冲突，请重试")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="编号生成失败")  # pragma: no cover

    # ---------- H02 列表 ----------

    @staticmethod
    def list_page(
        db: Session,
        *,
        status_: str | None = None,
        level: str | None = None,
        type_: str | None = None,
        keyword: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
        sort: str = "create_time",  # create_time | level（PRD H02 排序验收）
        order: str = "desc",        # asc | desc
    ) -> dict:
        """H02 隐患列表（PRD：分页 + 状态/等级/类型/时间区间/关键字筛选 + 排序）。"""
        items, total = HazardRepo.list_page(
            db, status=status_, level=level, type_=type_, keyword=keyword,
            start_time=start_time, end_time=end_time, page=page, page_size=page_size,
            sort=sort, order=order,
        )
        ids = [h.id for h in items]
        names = HazardService._user_names(db, {h.creator_id for h in items})
        counts = HazardService._image_counts(db, ids)
        return {
            "page": page, "page_size": page_size, "total": total,
            "items": [HazardService._item(h, names, counts) for h in items],
        }

    # ---------- H03 详情 ----------

    @staticmethod
    def get(db: Session, hid: int, user: User) -> dict:
        """H03 隐患详情（含图片 + 处理进度时间线）。PRD 透明度设计：登录用户可见全部。"""
        h = HazardRepo.get_by_id(db, hid)
        if h is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="隐患不存在")
        return HazardService._detail(db, h, user)

    # ---------- 管理员一键闭环 ----------

    @staticmethod
    def close(db: Session, hid: int, user: User) -> dict:
        """管理员/安全员将「待处理」隐患标记为「已闭环」（PRD H03 验收）。

        角色门禁在 api 层 require_roles，此处纵深防御复检；状态非 WAIT_PROCESS 拒绝（400）。
        单事务：改状态 + 落时间线日志（CLOSE，old→new 留痕）。
        """
        if user.role_id not in (RoleId.SAFETY, RoleId.ADMIN):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权操作")
        h = HazardRepo.get_by_id(db, hid)
        if h is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="隐患不存在")
        if h.status != HazardStatus.WAIT_PROCESS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"仅待处理状态的隐患可闭环（当前状态 {h.status}）",
            )
        HazardRepo.update_status(db, h, HazardStatus.FINISHED, commit=False)
        HazardRepo.add_log(
            db, h.id, user.id, HazardLogOperation.CLOSE,
            old_status=HazardStatus.WAIT_PROCESS, new_status=HazardStatus.FINISHED,
            remark="管理员确认闭环", commit=False,
        )
        db.commit()
        db.refresh(h)
        return {"message": "已闭环", "hazard_no": h.hazard_no, "status": h.status}

    # ---------- 组装 ----------

    @staticmethod
    def _detail(db: Session, h: Hazard, user: User) -> dict:
        names = HazardService._user_names(db, {h.creator_id})
        images = HazardRepo.get_images(db, h.id)
        logs = HazardRepo.get_logs(db, h.id)
        op_names = HazardService._user_names(db, {lg.operator_id for lg in logs})
        op_names.update(names)
        return {
            "id": h.id,
            "hazard_no": h.hazard_no,
            "title": h.title,
            "description": h.description,
            "location": h.location,
            "level": h.level,
            "type": h.type,
            "status": h.status,
            "creator_id": h.creator_id,
            "creator_name": names.get(h.creator_id, ""),
            # H04–H06 预留字段（本期恒空，详情展示占位）
            "handler_id": h.handler_id,
            "deadline": h.deadline.isoformat() if h.deadline else None,
            "rectification_measure": h.rectification_measure,
            "rectification_images": h.rectification_images,
            "reject_reason": h.reject_reason,
            "risk_report": h.risk_report,
            "images": [
                {"id": im.id, "image_url": im.image_url,
                 "uploader_id": im.uploader_id,
                 "create_time": im.create_time.isoformat() if im.create_time else None}
                for im in images
            ],
            "timeline": [
                {
                    "id": lg.id, "operation": lg.operation,
                    "operator_id": lg.operator_id,
                    "operator_name": op_names.get(lg.operator_id, ""),
                    "old_status": lg.old_status, "new_status": lg.new_status,
                    "remark": lg.remark,
                    "create_time": lg.create_time.isoformat() if lg.create_time else None,
                }
                for lg in logs
            ],
            "create_time": h.create_time.isoformat() if h.create_time else None,
            "update_time": h.update_time.isoformat() if h.update_time else None,
        }

    @staticmethod
    def _item(h: Hazard, names: dict[int, str], counts: dict[int, int]) -> dict:
        return {
            "id": h.id,
            "hazard_no": h.hazard_no,
            "title": h.title,
            "description": h.description,
            "location": h.location,
            "level": h.level,
            "type": h.type,
            "status": h.status,
            "creator_id": h.creator_id,
            "creator_name": names.get(h.creator_id, ""),
            "image_count": counts.get(h.id, 0),
            "create_time": h.create_time.isoformat() if h.create_time else None,
            "update_time": h.update_time.isoformat() if h.update_time else None,
        }

    @staticmethod
    def _user_names(db: Session, ids: set[int]) -> dict[int, str]:
        """批量查用户显示名（name，缺省回退 username）→ {user_id: 名}。"""
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = db.execute(
            select(User.id, User.name, User.username).where(User.id.in_(ids))
        ).all()
        return {uid: (name or username) for uid, name, username in rows}

    @staticmethod
    def _image_counts(db: Session, hazard_ids: list[int]) -> dict[int, int]:
        if not hazard_ids:
            return {}
        rows = db.execute(
            select(HazardImage.hazard_id, func.count(HazardImage.id))
            .where(HazardImage.hazard_id.in_(hazard_ids))
            .group_by(HazardImage.hazard_id)
        ).all()
        return {hid: cnt for hid, cnt in rows}

    @staticmethod
    def _auto_title(description: str) -> str:
        text = description.strip()
        return text[:20] + ("…" if len(text) > 20 else "")
