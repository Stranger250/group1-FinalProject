"""图片上传通用落盘（B03 白名单：jpg/png/jpeg ≤5MB）。

隐患现场图（hazard 模块）与用户头像（个人中心）共用同一套校验与落盘：
扩展名 + MIME 白名单、大小上限，落 backend/data/uploads/<日期>/<uuid>.<ext>，
经 main.py 挂载的 /uploads 静态访问。返回「日期子目录/文件名」相对路径（不含 /uploads 前缀）。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

_ALLOWED_EXTS = {".jpg", ".jpeg", ".png"}
_ALLOWED_MIMES = {"image/jpeg", "image/png"}


def save_image_upload(file: UploadFile, settings) -> str:
    """校验并落盘图片，返回相对路径（不含 /uploads 前缀）。

    校验失败抛 400（类型/大小），文件名 uuid 防碰撞/防路径穿越。
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_EXTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"仅支持 jpg/png/jpeg 图片，收到 {suffix or '未知类型'}",
        )
    if (file.content_type or "") not in _ALLOWED_MIMES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"非图片文件类型：{file.content_type}")

    data = file.file.read()
    max_bytes = int(settings.max_upload_mb * 1024 * 1024)
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"图片超过大小上限（{settings.max_upload_mb:.0f}MB）",
        )

    day = datetime.now().strftime("%Y%m%d")
    rel = f"{day}/{uuid.uuid4().hex}{suffix}"
    target = Path(settings.upload_dir) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return rel
