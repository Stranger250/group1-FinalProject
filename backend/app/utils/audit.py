"""关键操作审计日志（ARCHITECTURE §5.4/§10：登录、闭环、审核、发布、用户管理等关键操作留痕）。

- 表：audit_log（schema.sql 建表 + init_db.py 幂等迁移）；
- 用法：write_audit(db, user, action, target_type=None, target_id=None, detail=None, ip=None)；
- 设计：user_id/username 冗余存（操作人可能被删/禁用后仍可追溯）；
  detail 限长 500；写失败仅告警不阻断业务（审计不参与业务事务，独立 commit）。
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("audit")


def write_audit(
    db: Session,
    user,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | int | None = None,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    """写入一条审计日志。失败仅告警，不影响主业务流程（best-effort）。"""
    try:
        db.execute(
            text(
                "INSERT INTO audit_log (user_id, username, action, target_type, target_id, detail, ip) "
                "VALUES (:uid, :uname, :action, :ttype, :tid, :detail, :ip)"
            ),
            {
                "uid": getattr(user, "id", 0),
                "uname": (getattr(user, "username", None) or "")[:64],
                "action": action[:64],
                "ttype": (target_type or "")[:32] or None,
                "tid": str(target_id)[:64] if target_id is not None else None,
                "detail": (detail or "")[:500] or None,
                "ip": (ip or "")[:64] or None,
            },
        )
        db.commit()
    except Exception:  # noqa: BLE001 —— 审计失败不影响业务
        db.rollback()
        logger.exception("审计日志写入失败：action=%s", action)
