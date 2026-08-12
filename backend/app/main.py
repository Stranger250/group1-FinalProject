"""蜀道安全助手 FastAPI 入口。

启动：cd shudao/backend && uvicorn app.main:app --reload
文档：http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import sys

# Windows 控制台 GBK → UTF-8，避免中文报错乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import ai, auth, exam, exam_running, paper
from .utils.response import resp

app = FastAPI(
    title="蜀道安全助手 API",
    description="模块三 考试工坊（E01-E05）后端接口",
    version="0.1.0",
)

# 开发环境放开跨域；生产按 ARCHITECTURE §10 收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(exam.router)
app.include_router(ai.router)
app.include_router(paper.router)
app.include_router(exam_running.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail), "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 校验失败统一为 {code,message,data}（HTTP 422）。"""
    errs = exc.errors()
    if errs:
        loc = ".".join(str(x) for x in errs[0].get("loc", []))
        msg = errs[0].get("msg", "参数校验失败")
        message = f"{loc}: {msg}" if loc else msg
    else:
        message = "参数校验失败"
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": message, "data": None},
    )


@app.get("/", summary="健康检查")
def health():
    return resp({"status": "ok", "module": "考试工坊 backend"})
