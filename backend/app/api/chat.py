"""模块二 AI 智能助手接口（A01-A07）。

与 E02 的 api/ai.py（prefix /api/v1/ai）同前缀不同路径，互不冲突：
  E02 生成/审核类 仅管理员；本模块全部接口任意登录用户可用（get_current_user）。

约定：
- 统一响应 {code, message, data}（utils/response.resp）；
- POST /chat 走 SSE（text/event-stream，Cache-Control: no-cache），
  事件序 meta → delta* → done（契约 §0.1），业务错误在流开始前以 HTTP 状态码返回；
- 归属校验（会话/消息非本人）统一 404 掩码。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import get_current_user
from ..rag.sensitive import contains_sensitive
from ..schema.chat import ChatIn, ConversationUpdate, FeedbackIn
from ..service.chat_service import ChatService
from ..service.qa_service import QaService
from ..utils.response import resp

router = APIRouter(prefix="/api/v1/ai", tags=["AI 助手"])

# 全部接口需登录（任意角色）——直接在参数里 Depends(get_current_user)


@router.post("/chat", summary="智能问答（A01，SSE 流式）")
async def chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """RAG 智能问答：SSE 流返回 meta → delta* → done。

    - 敏感词预检在流开始前同步执行，命中抛 400（不进检索/LLM）；
    - conversation_id 为空自动建会话（首问标题=问题前 20 字）；
    - user 消息行在流开始前先落库（断线不丢历史）。
    """
    hits = contains_sensitive(payload.message)
    if hits:
        raise HTTPException(status_code=400, detail=f"内容包含敏感词：{'、'.join(hits)}")
    conv, _is_new = QaService.resolve_conversation(db, user, payload)
    user_msg_id, history = QaService.persist_user_message(db, conv, payload.message)

    async def gen():
        async for line in QaService.stream_qa(db, conv, user_msg_id, payload.message, history):
            yield line

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations", summary="新建会话（A02）")
def create_conversation(
    payload: ConversationUpdate | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """新建会话；body 可缺省（标题默认「新会话」）。"""
    title = payload.title if payload else None
    return resp(ChatService.create_conversation(db, user, title))


@router.get("/conversations", summary="会话列表（A02）")
def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return resp(ChatService.list_conversations(db, user, page=page, page_size=page_size))


@router.put("/conversations/{cid}", summary="重命名会话（A02）")
def rename_conversation(
    cid: int,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return resp(ChatService.rename_conversation(db, user, cid, payload.title))


@router.delete("/conversations/{cid}", summary="删除会话（A02，级联）")
def delete_conversation(
    cid: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    ChatService.delete_conversation(db, user, cid)
    return resp(message="会话已删除")


@router.get("/conversations/{cid}/messages", summary="会话消息列表（A02）")
def list_messages(
    cid: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return resp(ChatService.list_messages(db, user, cid))


@router.get("/source/{message_id}", summary="回答引用列表（A03）")
def get_sources(
    message_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return resp(ChatService.get_sources(db, user, message_id))


@router.get("/article", summary="查看原文（A03）")
def get_article(
    doc_id: str = Query(min_length=1),
    article_no: str = Query(min_length=1),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """doc_id+article_no → 父块全文（检索层父块索引，无需 DB 会话归属）。"""
    return resp(ChatService.get_article(db, user, doc_id, article_no))


@router.get("/quick-questions", summary="快捷提问（A04）")
def quick_questions(user=Depends(get_current_user)):
    return resp([q.model_dump() for q in ChatService.quick_questions()])


@router.post("/feedback/{message_id}", summary="回答反馈（A07）")
def set_feedback(
    message_id: int,
    payload: FeedbackIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """点赞/点踩：1=有用、-1=没用、0=清除；单行 UPDATE 幂等。"""
    ChatService.set_feedback(db, user, message_id, payload.value)
    return resp(message="反馈已记录")
