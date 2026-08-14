"""模块一 隐患安全管理 API（H01–H03，路由前缀 /api/v1/hazards，与现有前缀无冲突）。

分层：本文件是薄壳（路由 + 鉴权 + 参数解析 + 上传落盘），业务在 HazardService，
图片经 /uploads 静态访问（main.py 挂载 StaticFiles）。全部 return resp(...)。

- H01 上报 POST /hazards：任意登录用户；
- H02 列表 GET /hazards：任意登录用户（PRD 透明度设计）；
- H03 详情 GET /hazards/{id}：任意登录用户；
- 一键闭环 POST /hazards/{id}/close：SAFETY/ADMIN（require_roles）；
- 图片上传 POST /hazards/upload（B03：jpg/png/jpeg ≤5MB）；
- AI 识别 POST /hazards/analyze：上传并识别一张图，返回 url + 类型/等级/描述建议 + bbox 位置 + 标注图。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from ..ai.vision import VisionError, analyze_image, annotate_image
from ..core.config import get_settings
from ..core.database import get_db  # noqa: F401  # 与 Session 一起构成 get_db 依赖类型标注
from ..core.security import get_current_user, require_roles
from ..model.user import RoleId, User
from ..schema.hazard import HazardCheckIn, HazardCreate, HazardDispatchIn, HazardRectifyIn
from ..service.hazard_service import HazardService
from ..utils.response import resp
from ..utils.upload import save_image_upload

router = APIRouter(prefix="/api/v1/hazards", tags=["隐患安全管理 H01-H03"])

# 管理向接口门禁：闭环需 SAFETY/ADMIN（角色枚举 RoleId）
_MANAGE = require_roles(RoleId.SAFETY, RoleId.ADMIN)


# ---------- 图片上传 / AI 识别 ----------

@router.post("/upload", summary="H01 图片上传（B03：jpg/png/jpeg ≤5MB）")
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传隐患现场图片，落 backend/data/uploads，返回可访问的 /uploads/... URL。

    前端先调用本接口拿到 URL，随上报表单一起提交（images 列表）。
    """
    rel_path = save_image_upload(file, get_settings())
    return resp({"url": f"/uploads/{rel_path}"})


@router.post("/analyze", summary="H01 AI 视觉识别：上传一张图并返回隐患类型/等级/描述建议")
async def analyze(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传图片 → 视觉模型识别 → 返回 url + type/level/description + bbox + 标注图 annotated_url。

    bbox 为归一化坐标 [x1,y1,x2,y2]（无隐患为 null）；标注图是原图画好红色框的副本，
    两者都随 report 落 hazard.risk_report。前端可回显建议并展示标注图供用户确认。
    视觉模型未配置或调用失败 → 503 提示（不阻断上报，用户可手动选类型/等级）。
    """
    rel_path = save_image_upload(file, get_settings())
    try:
        result = await asyncio.wait_for(analyze_image(_upload_path(rel_path)), timeout=290.0)
    except VisionError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except asyncio.TimeoutError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="视觉识别超时，请重试或跳过")

    # 把每处隐患 bbox 画到原图上生成多框标注图（无有效框时为 None），URL 同时写进 report 随 risk_report 落库
    annotated_rel = annotate_image(_upload_path(rel_path), result["detections"])
    annotated_url = f"/uploads/{annotated_rel}" if annotated_rel else None
    report = dict(result["report"])
    if annotated_url:
        report["annotated_url"] = annotated_url

    return resp({
        "url": f"/uploads/{rel_path}",
        "type_suggest": result["type_suggest"],
        "level_suggest": result["level_suggest"],
        "description": result["description"],
        "reason": result["reason"],          # 识别依据（为什么判为该类型），供前端回显/排查
        "confidence": result["confidence"],
        "bbox": result["bbox"],              # 主检测归一化 [x1,y1,x2,y2]；无隐患时为 null
        "detections": result["detections"],  # 全部检测项（每处含 type/level/bbox/description/reason/confidence）
        "annotated_url": annotated_url,      # 标注图（多框+编号）URL，无有效框时为 null
        "report": report,
    })


# ---------- H01 上报 / H02 列表 / H03 详情 / 闭环 ----------

@router.post("", summary="H01 隐患上报")
def create_hazard(
    payload: HazardCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交隐患（描述/等级必填），生成唯一编号，状态待处理，落时间线。返回完整详情。"""
    return resp(HazardService.create(db, payload, user))


@router.get("", summary="H02 隐患列表（筛选 + 分页）")
def list_hazards(
    status_: str | None = Query(default=None, alias="status", description="状态：WAIT_PROCESS/FINISHED"),
    level: str | None = Query(default=None, description="等级：CRITICAL/MAJOR/GENERAL/MINOR"),
    type_: str | None = Query(default=None, alias="type", description="类型：高处作业/用电安全/…"),
    keyword: str | None = Query(default=None, description="关键字：匹配标题/描述/位置"),
    start_time: Annotated[datetime | None, Query(description="上报时间区间起点（ISO）")] = None,
    end_time: Annotated[datetime | None, Query(description="上报时间区间终点（ISO）")] = None,
    sort: str = Query(default="create_time", pattern="^(create_time|level)$", description="排序字段：create_time/level"),
    order: str = Query(default="desc", pattern="^(asc|desc)$", description="排序方向：asc/desc"),
    page: int = Query(default=1, ge=1, le=100000),      # 上限防 MySQL OFFSET 溢出
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(HazardService.list_page(
        db, status_=status_, level=level, type_=type_, keyword=keyword,
        start_time=start_time, end_time=end_time, page=page, page_size=page_size,
        sort=sort, order=order,
    ))


@router.get("/{hid}", summary="H03 隐患详情（含图片 + 处理进度时间线）")
def get_hazard(
    hid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resp(HazardService.get(db, hid, user))


@router.post("/{hid}/close", summary="H03 管理员一键闭环（SAFETY/ADMIN）")
def close_hazard(
    hid: int,
    user: User = Depends(_MANAGE),
    db: Session = Depends(get_db),
):
    """待处理 → 已闭环，落时间线日志（old→new 留痕）。"""
    return resp(HazardService.close(db, hid, user))


# ---------- H04 派单 / H05 整改 / H06 验收 ----------

@router.post("/{hid}/dispatch", summary="H04 派单：指定整改负责人与期限（SAFETY/ADMIN）")
def dispatch_hazard(
    hid: int,
    payload: HazardDispatchIn,
    user: User = Depends(_MANAGE),
    db: Session = Depends(get_db),
):
    """待处理 → 处理中，落派单人/负责人/期限与时间线日志。"""
    return resp(HazardService.dispatch(db, hid, user, **payload.model_dump()))


@router.post("/{hid}/rectify", summary="H05 整改反馈：提交整改措施与照片")
def rectify_hazard(
    hid: int,
    payload: HazardRectifyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """处理中 → 待验收（整改负责人本人或 SAFETY/ADMIN），落整改内容与时间线日志。"""
    return resp(HazardService.rectify(db, hid, user, **payload.model_dump()))


@router.post("/{hid}/check", summary="H06 验收：通过闭环 / 驳回（SAFETY/ADMIN）")
def check_hazard(
    hid: int,
    payload: HazardCheckIn,
    user: User = Depends(_MANAGE),
    db: Session = Depends(get_db),
):
    """待验收 → 已闭环（通过）或已驳回（不通过需原因），落时间线日志。"""
    return resp(HazardService.check(db, hid, user, **payload.model_dump()))


# ---------- 文件落盘 ----------

def _upload_path(rel: str) -> Path:
    """相对路径 → 磁盘绝对路径（save_image_upload 存储 / analyze 读取同口径）。"""
    return Path(get_settings().upload_dir) / rel
