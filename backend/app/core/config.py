"""应用配置（pydantic-settings 读 backend/.env）。

约定：每文件夹一份 .env，从 shudao/backend 目录运行（uvicorn / scripts 均在 backend 下）。
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 已知的公开占位密钥（源码默认值 / .env.example 示例）。命中任一即视为未配置，
# 运行时改用 secrets 生成随机密钥，杜绝「知晓源码即可离线伪造 JWT」的全量越权（#9）。
_PLACEHOLDER_SECRETS = {"", "dev-only-change-me", "dev-only-change-me-please-random-64-char"}

# backend/.env 的绝对路径：config.py 位于 backend/app/core/，父级两级即 backend。
# 用绝对路径保证无论从哪个目录运行（如 shudao 根目录直接跑 scripts/），
# 都能读到本文件夹的 .env，而不是误落默认值（root:password → 1045）。
ENV_FILE = str(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseSettings):
    # ===== MySQL（对齐 DATABASE.md §9，库名 shudao）=====
    database_url: str = "mysql+pymysql://root:password@127.0.0.1:3306/shudao?charset=utf8mb4"

    # ===== Redis（E04 考试会话用）=====
    redis_url: str = "redis://127.0.0.1:6379/0"

    # ===== JWT（B01/B02）=====
    jwt_secret: str = ""
    jwt_expire_minutes: int = 120
    jwt_algorithm: str = "HS256"

    def model_post_init(self, __context) -> None:
        """密钥防占位：.env 缺省或仍为公开占位串时，用 secrets 生成随机密钥。

        随机密钥不持久化，进程重启后旧 token 全部失效（需重新登录）——
        对培训项目可接受，换来「源码/示例不可伪造令牌」的确定性安全。
        """
        if self.jwt_secret in _PLACEHOLDER_SECRETS:
            self.jwt_secret = secrets.token_urlsafe(48)

    # ===== 初始化账号（Phase0 init_db.py 写入）=====
    admin_username: str = "admin"
    admin_password: str = "Admin@123456"

    # ===== E02 出题（Phase2 启用）=====
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""
    law_json_dir: str = "../crawler_output"
    gen_min_count: int = 5

    model_config = SettingsConfigDict(
        env_file=(ENV_FILE,),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
