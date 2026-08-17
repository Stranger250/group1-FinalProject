"""审计日志查询接口（ADMIN）：分页 + 筛选（动作/操作人/时间区间）+ 上报报文预留接口（B2）。

审计写入见 app/utils/audit.py（best-effort 不阻断业务）；
查询面：action 白名单 + keyword 匹配 username/detail + create_time 区间。
B2：POST /logs/report 仅返回标准 JSON 报文（OA 对接预留，配置 oa_report_url 后由对接方消费）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.database import get_db
from ..core.security import require_roles
from ..model.user import RoleId, User
from ..utils.response import resp

router = APIRouter(prefix="/api/v1/logs", tags=["审计日志"])

_ADMIN = require_roles(RoleId.ADMIN)


@router.get("", summary="审计日志列表（ADMIN，分页 + 筛选）")
def list_logs(
    action: str | None = Query(default=None, description="动作，如 login/hazard_close/exam_submit"),
    keyword: str | None = Query(default=None, description="操作人/详情关键字"),
    start_time: Annotated[datetime | None, Query(description="起始时间（ISO）")] = None,
    end_time: Annotated[datetime | None, Query(description="结束时间（ISO）")] = None,
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(_ADMIN),
):
    from sqlalchemy import text
    conds = []
    params: dict = {}
    if action:
        conds.append("action = :action")
        params["action"] = action[:64]
    if keyword:
        conds.append("(username LIKE :kw OR detail LIKE :kw)")
        params["kw"] = f"%{keyword}%"
    if start_time:
        conds.append("create_time >= :st")
        params["st"] = start_time
    if end_time:
        conds.append("create_time <= :et")
        params["et"] = end_time
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    total = db.execute(text(f"SELECT COUNT(*) FROM audit_log{where}"), params).scalar() or 0
    rows = db.execute(
        text(
            f"SELECT id, user_id, username, action, target_type, target_id, detail, ip, create_time "
            f"FROM audit_log{where} ORDER BY id DESC "
            f"LIMIT :lim OFFSET :off"
        ),
        {**params, "lim": page_size, "off": (page - 1) * page_size},
    ).all()
    return resp({
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                "id": r[0],
                "user_id": r[1],
                "username": r[2],
                "action": r[3],
                "target_type": r[4],
                "target_id": r[5],
                "detail": r[6],
                "ip": r[7],
                "create_time": r[8].isoformat() if r[8] else None,
            }
            for r in rows
        ],
    })


@router.post("/report", summary="B2 日志上报报文（ADMIN，OA 对接预留接口）")
def report_logs(
    start_time: Annotated[datetime | None, Query(description="起始时间（ISO），缺省=最近 24 小时")] = None,
    end_time: Annotated[datetime | None, Query(description="结束时间（ISO）")] = None,
    action: str | None = Query(default=None, description="按动作过滤（可选）"),
    db: Session = Depends(get_db),
    user: User = Depends(_ADMIN),
):
    """按时间区间/动作拉取审计日志并序列化为标准 JSON 报文（对接契约）。

    本期仅返回报文（不发起外部 HTTP 调用）；oa_report_url 配置后由未来 OA 对接方消费。
    调用留审计（action=logs_report）。
    """
    from sqlalchemy import text

    conds = []
    params: dict = {}
    if start_time:
        conds.append("create_time >= :st")
        params["st"] = start_time
    if end_time:
        conds.append("create_time <= :et")
        params["et"] = end_time
    if action:
        conds.append("action = :action")
        params["action"] = action[:64]
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    rows = db.execute(
        text(
            f"SELECT id, user_id, username, action, target_type, target_id, detail, ip, create_time "
            f"FROM audit_log{where} ORDER BY id ASC LIMIT 5000"
        ),
        params,
    ).all()
    payload = {
        "source": "shudao-safety-assistant",
        "version": "1.0",
        "period": {
            "start": start_time.isoformat() if start_time else None,
            "end": end_time.isoformat() if end_time else None,
        },
        "item_count": len(rows),
        "items": [
            {
                "id": r[0], "user_id": r[1], "username": r[2], "action": r[3],
                "target_type": r[4], "target_id": r[5], "detail": r[6], "ip": r[7],
                "create_time": r[8].isoformat() if r[8] else None,
            }
            for r in rows
        ],
    }
    from ..utils.audit import write_audit
    write_audit(db, user, "logs_report", target_type="log",
                detail=f"period={start_time}~{end_time} action={action or '*'}")
    # 配置占位：oa_report_url 为空时仅返回报文（B2 本期不实现推送）
    oa_url = get_settings().oa_report_url
    return resp({"oa_report_url_configured": bool(oa_url), "payload": payload})
