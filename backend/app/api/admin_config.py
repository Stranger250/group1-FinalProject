"""O9 管理端配置接口：模型配置 + RAG 分块策略（读写 app_config 表，即时生效）。

- GET  /admin/config/models  模型配置（LLM/VISION，api_key 脱敏）
- PUT  /admin/config/models  保存模型配置（写 app_config，cache_clear 即时生效）
- GET  /admin/config/rag     RAG 检索/分块参数（当前生效值）
- PUT  /admin/config/rag     保存 RAG 参数（写 app_config；分块参数需重建知识库生效）

权限：模型管理 ADMIN；RAG 策略 SAFETY/ADMIN（PRD O9 权限细化）。
敏感字段（api_key）仅存 DB（app_config 表，不落 git），GET 回显脱敏。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from ..core.config import get_settings
from ..core.database import get_db
from ..core.security import require_roles
from ..model.user import RoleId
from ..utils.response import resp

router = APIRouter(prefix="/api/v1/admin/config", tags=["O9 配置管理"])

_ADMIN = require_roles(RoleId.ADMIN)
_MANAGE = require_roles(RoleId.SAFETY, RoleId.ADMIN)

# app_config 表 key 白名单（与 Settings._OVERRIDE_KEYS 对齐）
_LLM_KEYS = ("base_url", "api_key", "model_name")
_VISION_KEYS = ("vision_base_url", "vision_api_key", "vision_model_name")
_RAG_KEYS = (
    "rag_vector_top_k", "rag_bm25_top_k", "rag_rrf_k", "rag_fusion_top_k",
    "rag_rerank_top_n", "rag_conf_refuse", "rag_conf_conservative",
    "rag_vec_sim_floor", "rag_parent_split_chars", "rag_child_min_chars",
    "rag_child_max_chars",
)


def _mask_secret(v: str | None) -> str:
    """api_key 脱敏：sk-abc…wxyz → sk-***wxyz（保留前 3 后 4）。"""
    if not v:
        return ""
    if len(v) <= 8:
        return "*" * len(v)
    return v[:3] + "*" * (len(v) - 7) + v[-4:]


def _read_override(key: str) -> str | None:
    """读 app_config 单 key（无则 None）。"""
    db = next(get_db())
    try:
        row = db.execute(
            text("SELECT `value` FROM app_config WHERE `key` = :k"), {"k": key}
        ).fetchone()
        return row[0] if row else None
    finally:
        db.close()


def _write_overrides(db, kv: dict[str, object]) -> None:
    """upsert 多个 key 到 app_config（value JSON 序列化保类型）。"""
    for key, value in kv.items():
        db.execute(
            text(
                "INSERT INTO app_config (`key`, `value`, updated_at) VALUES (:k, :v, NOW()) "
                "ON DUPLICATE KEY UPDATE `value` = :v, updated_at = NOW()"
            ),
            {"k": key, "v": json.dumps(value, ensure_ascii=False)},
        )
    db.commit()


def _delete_overrides(db, keys: list[str]) -> None:
    """删除 key（传空串 = 恢复默认）。"""
    for key in keys:
        db.execute(text("DELETE FROM app_config WHERE `key` = :k"), {"k": key})
    db.commit()


# ---------- 模型管理（ADMIN） ----------

class ModelsIn(BaseModel):
    base_url: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None, max_length=512)
    model_name: str | None = Field(default=None, max_length=128)
    vision_base_url: str | None = Field(default=None, max_length=512)
    vision_api_key: str | None = Field(default=None, max_length=512)
    vision_model_name: str | None = Field(default=None, max_length=128)


@router.get("/models", summary="O9 模型配置（LLM/VISION，api_key 脱敏）")
def get_models(_=Depends(_ADMIN)):
    s = get_settings()
    return resp({
        "llm": {
            "base_url": s.base_url,
            "api_key_masked": _mask_secret(s.api_key),
            "api_key_set": bool(s.api_key),
            "model_name": s.model_name,
        },
        "vision": {
            "base_url": s.vision_base_url,
            "api_key_masked": _mask_secret(s.vision_api_key),
            "api_key_set": bool(s.vision_api_key),
            "model_name": s.vision_model_name,
        },
    })


@router.put("/models", summary="O9 保存模型配置（写 app_config，即时生效）")
def save_models(payload: ModelsIn, db=Depends(get_db), _=Depends(_ADMIN)):
    kv: dict[str, object] = {}
    delete_keys: list[str] = []
    for key, value in payload.model_dump().items():
        if value is None:
            continue  # 未传字段不修改
        if str(value).strip() == "":
            delete_keys.append(key)  # 清空 = 恢复默认
        else:
            kv[key] = str(value).strip()
    if kv:
        _write_overrides(db, kv)
    if delete_keys:
        _delete_overrides(db, delete_keys)
    get_settings.cache_clear()  # 即时生效（llm_client 实时读 settings）
    s = get_settings()
    return resp({
        "message": "模型配置已保存并生效",
        "llm": {
            "base_url": s.base_url,
            "api_key_masked": _mask_secret(s.api_key),
            "model_name": s.model_name,
        },
        "vision": {
            "base_url": s.vision_base_url,
            "api_key_masked": _mask_secret(s.vision_api_key),
            "model_name": s.vision_model_name,
        },
    })


# ---------- RAG 策略（SAFETY/ADMIN） ----------

class RagIn(BaseModel):
    rag_vector_top_k: int | None = Field(default=None, ge=10, le=200)
    rag_bm25_top_k: int | None = Field(default=None, ge=10, le=200)
    rag_rrf_k: int | None = Field(default=None, ge=10, le=200)
    rag_fusion_top_k: int | None = Field(default=None, ge=5, le=100)
    rag_rerank_top_n: int | None = Field(default=None, ge=1, le=20)
    rag_conf_refuse: float | None = Field(default=None, ge=0.0, le=1.0)
    rag_conf_conservative: float | None = Field(default=None, ge=0.0, le=1.0)
    rag_vec_sim_floor: float | None = Field(default=None, ge=0.0, le=1.0)
    rag_parent_split_chars: int | None = Field(default=None, ge=200, le=2000)
    rag_child_min_chars: int | None = Field(default=None, ge=50, le=1000)
    rag_child_max_chars: int | None = Field(default=None, ge=100, le=2000)


@router.get("/rag", summary="O9 RAG 检索/分块参数（当前生效值）")
def get_rag(_=Depends(_MANAGE)):
    s = get_settings()
    return resp({k: getattr(s, k) for k in _RAG_KEYS})


@router.put("/rag", summary="O9 保存 RAG 参数（分块参数需重建知识库生效）")
def save_rag(payload: RagIn, db=Depends(get_db), _=Depends(_MANAGE)):
    kv = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not kv:
        raise HTTPException(status_code=400, detail="未提交任何参数")
    _write_overrides(db, kv)
    get_settings.cache_clear()
    # 分块参数变化提示重建（O5：仅构建时读取）
    split_keys = {"rag_parent_split_chars", "rag_child_min_chars", "rag_child_max_chars"}
    need_rebuild = bool(split_keys & set(kv))
    return resp({
        "message": "RAG 参数已保存" + ("，分块参数已变更：需重建知识库后对长条二次分块生效" if need_rebuild else "，检索参数即时生效"),
        "need_rebuild": need_rebuild,
    })
