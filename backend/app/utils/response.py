"""统一响应结构：{code, message, data}

约定：
- 业务成功 code=200；
- 业务失败（参数不合法等）抛 HTTPException，由 main.py 全局异常处理器统一转成 {code, message, data:null}；
- 未登录 401、越权 403、不存在 404。
"""
from __future__ import annotations

from typing import Any


def resp(data: Any = None, message: str = "success", code: int = 200) -> dict[str, Any]:
    """构造统一响应体。"""
    return {"code": code, "message": message, "data": data}
