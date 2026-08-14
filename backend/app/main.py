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

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .api import ai, auth, chat, exam, exam_running, hazard, log, paper, user
from .core.config import get_settings
from .rag.embedder import get_embedder
from .rag.reranker import get_reranker
from .rag.retriever import get_retriever
from .rag.sensitive import load_sensitive_words
from .service.chat_service import load_quick_questions
from .utils.response import resp

logger = logging.getLogger("uvicorn.error")


def _warmup(name: str, fn) -> None:
    """预热一项：加载失败仅告警不阻断启动（chat 接口届时返回 500 而非崩启动）。"""
    t0 = time.time()
    try:
        fn()
        logger.info("[预热] %s 完成（%.1fs）", name, time.time() - t0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[预热] %s 失败：%s", name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动预热：加载嵌入/精排模型 + 检索索引（冷启动慢，预热消除首个请求卡顿）。"""
    async def _warmup_all() -> None:
        # 同步阻塞加载放线程池，避免阻塞事件循环
        await asyncio.to_thread(_warmup, "嵌入模型", get_embedder)
        await asyncio.to_thread(_warmup, "精排模型", get_reranker)
        await asyncio.to_thread(_warmup, "检索索引(BM25+Chroma)", get_retriever)
        _warmup("敏感词库", load_sensitive_words)
        _warmup("快捷提问", load_quick_questions)
        logger.info("[预热] 全部完成，AI 助手就绪")

    await _warmup_all()
    yield


app = FastAPI(
    title="蜀道安全助手 API",
    description="模块一 隐患安全管理（H01-H03）+ 模块二 AI 智能助手（A01-A07）+ 模块三 考试工坊（E01-E05）后端接口",
    version="0.1.0",
    lifespan=lifespan,
)

# 隐患图片上传目录（B03）：目录不存在则先创建（StaticFiles 要求目录已存在），
# 目录本身在 backend/data/uploads（.gitignore，构建产物不入库）
_upload_dir = Path(get_settings().upload_dir)
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_dir)), name="uploads")

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
app.include_router(chat.router)
app.include_router(hazard.router)
app.include_router(user.router)
app.include_router(log.router)


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
