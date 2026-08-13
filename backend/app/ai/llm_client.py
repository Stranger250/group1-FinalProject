"""OpenAI 兼容协议 LLM 客户端（E02 AI 出题的生成层）。

base_url / api_key / model_name 全部经 get_settings() 实时读取（backend/.env），
任一为空即视为未配置，抛 LLMError。

调用约定（对齐 AI_SOLUTION §6）：
- 对外只暴露 chat_json：传 system / user，返回已解析为 dict 的 JSON；
- 网络/限流类错误按指数退避重试（base 2s，默认 max_retries=2 次）；
- 响应剥掉 fenced code block 围栏后仍不是合法 JSON 时直接抛 LLMError，不在本层重试——
  “解析失败重试”由上层 E02 生成流程负责（Pydantic 校验不过时重新出题，最多 2 次）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 可重试的网络/限流类错误（指数退避重试）；其余 OpenAIError 视为不可重试，直接抛 LLMError。
# APIStatusError 覆盖 4xx/5xx（429 已被 RateLimitError 先行匹配，同属此元组无重复影响）。
_RETRYABLE = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    APIStatusError,
    httpx.HTTPError,
)

# Markdown 代码块围栏：```（可带 json/text 等语言标记）…```
_FENCE_RE = re.compile(r"```[ \t]*[A-Za-z0-9_-]*[ \t]*\r?\n(.*?)```", re.DOTALL)


class LLMError(Exception):
    """LLM 调用失败或响应解析失败。"""


async def chat_json(
    system: str,
    user: str,
    temperature: float = 0.3,
    max_retries: int = 2,
) -> dict[str, Any]:
    """调用 OpenAI 兼容 chat.completions（非流式），返回解析后的 JSON dict。

    - settings 用 get_settings() 实时取；BASE_URL/API_KEY/MODEL_NAME 任一为空抛 LLMError；
    - 先剥 fenced code block 围栏再 json.loads，解析失败抛 LLMError（不重试）；
    - 网络/限流错误按指数退避（2^attempt 秒，base 2s）重试 max_retries 次。
    """
    settings = get_settings()
    if not (settings.base_url and settings.api_key and settings.model_name):
        raise LLMError("LLM 未配置：请填写 .env 的 BASE_URL/API_KEY/MODEL_NAME")

    try:
        client = AsyncOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=120.0,
            max_retries=0,  # 重试策略由本函数统一控制（指数退避），不用 SDK 自带重试
        )
    except ValueError as exc:
        raise LLMError(f"LLM 配置错误：{exc}") from exc

    last_exc: Exception | None = None
    try:
        for attempt in range(max_retries + 1):
            try:
                response = await client.chat.completions.create(
                    model=settings.model_name,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    stream=False,
                )
                if not response.choices:
                    raise LLMError("LLM 响应没有 choices")
                content = (response.choices[0].message.content or "").strip()
                if not content:
                    raise LLMError("LLM 响应内容为空")
                return _extract_json(content)
            except LLMError:
                raise  # 解析失败不重试，交由上层处理
            except _RETRYABLE as exc:
                last_exc = exc
                logger.warning("LLM 调用失败（第 %s 次）：%s", attempt + 1, exc)
                if attempt < max_retries:
                    await asyncio.sleep(2 ** (attempt + 1))  # 2s、4s、8s…
            except OpenAIError as exc:
                # 鉴权/参数/服务端不可重试错误，直接失败
                raise LLMError(f"LLM 调用失败：{exc}") from exc
        raise LLMError(f"LLM 调用多次失败（已重试 {max_retries} 次）：{last_exc}")
    finally:
        await client.close()


async def chat_stream(
    system: str,
    user: str,
    temperature: float = 0.1,
    max_tokens: int = 800,
    max_retries: int = 1,
) -> AsyncIterator[str]:
    """OpenAI 兼容 chat.completions 流式（模块二 A01 SSE delta 数据源）。

    与 chat_json 的区别：
    - stream=True，逐 chunk 从 choices[0].delta.content 取增量文本 yield；
    - 重试只在「首块之前」进行（网络错误尚未出流 → 指数退避重试）；
      已出流后 SSE 断点续传不可靠，任何中断直接抛 LLMError，由 qa_service 落 FAILED。
    """
    settings = get_settings()
    if not (settings.base_url and settings.api_key and settings.model_name):
        raise LLMError("LLM 未配置：请填写 .env 的 BASE_URL/API_KEY/MODEL_NAME")
    try:
        client = AsyncOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=120.0,
            max_retries=0,  # 重试策略由本函数统一控制
        )
    except ValueError as exc:
        raise LLMError(f"LLM 配置错误：{exc}") from exc

    started = False
    last_exc: Exception | None = None
    try:
        for attempt in range(max_retries + 1):
            try:
                stream = await client.chat.completions.create(
                    model=settings.model_name,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
                async for chunk in stream:
                    started = True
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    piece = delta.content if delta else None
                    if piece:
                        yield piece
                return
            except _RETRYABLE as exc:
                last_exc = exc
                if started:
                    raise LLMError(f"LLM 流中断（已出流）：{exc}") from exc
                logger.warning("LLM 流式调用失败（第 %s 次）：%s", attempt + 1, exc)
                if attempt < max_retries:
                    await asyncio.sleep(2 ** (attempt + 1))  # 2s、4s…
            except OpenAIError as exc:
                raise LLMError(f"LLM 调用失败：{exc}") from exc
        raise LLMError(f"LLM 流式调用多次失败（已重试 {max_retries} 次）：{last_exc}")
    finally:
        await client.close()


def _extract_json(content: str) -> dict[str, Any]:
    """把 LLM 响应文本解析为 JSON dict。

    先剥掉 fenced code block 围栏（```…```，支持 json/text/纯 ``` 标记），
    再 json.loads；解析失败或顶层不是对象时抛 LLMError。
    """
    text = content.strip()
    if not text:
        raise LLMError("LLM 响应内容为空")
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise LLMError(f"LLM 响应不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise LLMError(f"LLM 响应 JSON 顶层不是对象（{type(data).__name__}）")
    return data
