"""考试工坊 E04 在线考试 + E05 自动阅卷接口。

与 E01 题库接口（api/exam.py，_MANAGE 门禁）分离：
- 考试接口面向所有登录用户（get_current_user，员工即可参加考试）；
- 归属校验（record.user_id == 当前用户）在 service 层统一 404/403；
- GET resume 带写副作用（超时自动交卷），响应加 Cache-Control: no-store；
- 交卷后任何 save/submit/switch/resume 幂等返回既有成绩单（service 层保证）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import get_current_user
from ..model.user import User
from ..schema.exam import ExamAnswersIn, ExamStartIn, ExamSwitchIn
from ..service.exam_service import ExamService
from ..utils.response import resp

router = APIRouter(prefix="/api/v1/exams", tags=["考试工坊 E04/E05 在线考试"])


# 静态前缀路由必须注册在 /{record_id} 之前：FastAPI 按注册顺序匹配，
# /exams/papers、/exams/records 若命中 int 型 {record_id} 会 422 而非落到下方静态路由。


@router.get("/papers", summary="公开选卷列表（仅已发布，脱敏无题目，前端 /exams 选卷页）")
def list_published_papers(
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return resp(ExamService.list_published_papers(db, user, page=page, page_size=page_size))


@router.get("/records", summary="我的考试记录（分页，前端 /exams/records 页）")
def list_my_records(
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return resp(ExamService.list_my_records(db, user, page=page, page_size=page_size))


@router.post("/start", summary="开始考试（或刷新复用进行中的考试）")
def start(
    payload: ExamStartIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return resp(ExamService.start(db, payload, user))


@router.get("/{record_id}", summary="刷新恢复（进行中返回题目+已存答案，已交卷返回成绩单）")
def resume(
    record_id: int,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "no-store"
    return resp(ExamService.resume(db, record_id, user))


@router.post("/{record_id}/save", summary="保存答案（增量自动保存）")
def save(
    record_id: int,
    payload: ExamAnswersIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return resp(ExamService.save(db, record_id, user, payload))


@router.post("/{record_id}/submit", summary="交卷 + 自动阅卷")
def submit(
    record_id: int,
    payload: ExamAnswersIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return resp(ExamService.submit(db, record_id, user, payload))


@router.post("/{record_id}/switch", summary="切屏上报（超过 3 次自动交卷）")
def switch(
    record_id: int,
    payload: ExamSwitchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return resp(ExamService.switch(db, record_id, user, payload))


@router.get("/{record_id}/result", summary="成绩单（交卷后，含答案与解析）")
def result(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return resp(ExamService.result(db, record_id, user))
