"""模块一 隐患安全管理数据访问（对应 DATABASE.md §4 三张表）。

风格照 repository/question_repo.py：静态方法类 + commit-per-method。
例外：create/add_images/add_log 支持 commit=False——H01 上报要把
「隐患主表 + 图片行 + 时间线日志」放进同一个事务（要么整条上报落库、要么整条回滚），
事务边界由 HazardService.create 控制。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..model.hazard import Hazard, HazardImage, HazardLevel, HazardLog

# 等级严重度排序权重（PRD H02 验收「按等级排序」）：CRITICAL 最重在前
_LEVEL_RANK = case(
    {HazardLevel.CRITICAL: 0, HazardLevel.MAJOR: 1, HazardLevel.GENERAL: 2, HazardLevel.MINOR: 3},
    value=Hazard.level,
    else_=4,
)


class HazardRepo:
    # ---------- 查询 ----------

    @staticmethod
    def get_by_id(db: Session, hid: int) -> Hazard | None:
        return db.scalar(select(Hazard).where(Hazard.id == hid))

    @staticmethod
    def get_images(db: Session, hid: int) -> list[HazardImage]:
        return list(db.scalars(
            select(HazardImage).where(HazardImage.hazard_id == hid)
            .order_by(HazardImage.id.asc())
        ))

    @staticmethod
    def get_logs(db: Session, hid: int) -> list[HazardLog]:
        """H03 处理进度时间线：按时间倒序（最新节点在前）。"""
        return list(db.scalars(
            select(HazardLog).where(HazardLog.hazard_id == hid)
            .order_by(HazardLog.create_time.desc(), HazardLog.id.desc())
        ))

    @staticmethod
    def count_by_no_prefix(db: Session, prefix: str) -> int:
        """统计编号前缀相同的隐患数，用于生成当日自增序号（HZ20260813-0001）。"""
        return db.scalar(
            select(func.count(Hazard.id)).where(Hazard.hazard_no.like(f"{prefix}%"))
        ) or 0

    @staticmethod
    def list_page(
        db: Session,
        *,
        status: str | None = None,
        level: str | None = None,
        type_: str | None = None,
        keyword: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        creator_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
        sort: str = "create_time",   # create_time | level（PRD H02 排序验收）
        order: str = "desc",         # asc | desc
    ) -> tuple[list[Hazard], int]:
        """H02 隐患列表：多条件筛选 + 分页（对齐 question_repo.list_page 模板）。

        keyword 模糊匹配 title/description/location；create_time 时间区间为 [start, end]。
        creator_id 非空时限定本人（如需「仅本人」可见性）。
        sort=level 时按严重度权重（CRITICAL>MAJOR>GENERAL>MINOR）排序；
        sort=create_time 时新上报在前（desc）或旧在前（asc），id 作次级排序键保证稳定。
        """
        conds = []
        if status:
            conds.append(Hazard.status == status)
        if level:
            conds.append(Hazard.level == level)
        if type_:
            conds.append(Hazard.type == type_)
        if keyword:
            like = f"%{keyword}%"
            conds.append(or_(
                Hazard.title.like(like),
                Hazard.description.like(like),
                Hazard.location.like(like),
            ))
        if start_time:
            conds.append(Hazard.create_time >= start_time)
        if end_time:
            conds.append(Hazard.create_time <= end_time)
        if creator_id:
            conds.append(Hazard.creator_id == creator_id)

        total = db.scalar(select(func.count(Hazard.id)).where(*conds)) or 0

        # 排序键：等级用严重度权重表达式；时间用 create_time，均以 id 作次级键保证同值稳定有序
        if sort == "level":
            order_col = _LEVEL_RANK
            tie_col = Hazard.id.desc()
        else:  # create_time（默认）
            order_col = Hazard.create_time
            tie_col = Hazard.id.desc()
        primary = order_col.desc() if order == "desc" else order_col.asc()
        items = list(db.scalars(
            select(Hazard).where(*conds)
            .order_by(primary, tie_col)
            .offset((page - 1) * page_size).limit(page_size)
        ))
        return items, total

    # ---------- 写入 ----------

    @staticmethod
    def create(db: Session, *, commit: bool = True, **kwargs) -> Hazard:
        h = Hazard(**kwargs)
        db.add(h)
        db.flush()  # 拿自增 id（供 add_images/add_log 引用）
        if commit:
            db.commit()
            db.refresh(h)
        return h

    @staticmethod
    def add_images(
        db: Session, hazard_id: int, urls: list[str], uploader_id: int,
        *, commit: bool = True,
    ) -> None:
        if not urls:
            return
        db.add_all([
            HazardImage(hazard_id=hazard_id, image_url=url, uploader_id=uploader_id)
            for url in urls
        ])
        if commit:
            db.commit()

    @staticmethod
    def add_log(
        db: Session, hazard_id: int, operator_id: int, operation: str,
        *, old_status: str | None = None, new_status: str | None = None,
        remark: str | None = None, commit: bool = True,
    ) -> HazardLog:
        log = HazardLog(
            hazard_id=hazard_id, operator_id=operator_id, operation=operation,
            old_status=old_status, new_status=new_status, remark=remark,
        )
        db.add(log)
        db.flush()
        if commit:
            db.commit()
        return log

    @staticmethod
    def update_status(db: Session, h: Hazard, new_status: str, *, commit: bool = True) -> Hazard:
        """状态流转（本期只有 WAIT_PROCESS → FINISHED），更新后落时间线日志由 service 负责。"""
        h.status = new_status
        if commit:
            db.commit()
            db.refresh(h)
        return h
