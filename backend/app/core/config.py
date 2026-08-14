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
    # AI 出题单次请求上限（schema/ai.py 校验真源）。模型单次输出 token 有上限，
    # 超出 20 题由 gen_service 分轮生成（每轮 ≤ gen_chunk_size，合并进同一 batch）。
    gen_max_count: int = 50
    # 分轮生成单轮题量：20 为实测安全上限（单轮输出 ~1.2 万字符 ≈ 1 万+ token，已被 20 题批次证明可行）
    gen_chunk_size: int = 20

    # ===== 模块一 隐患视觉识别（阿里云百炼 OpenAI 兼容端点，H01 图片识别）=====
    # 与 E02/A01 的 LLM（base_url/api_key/model_name）隔离，独立 VISION_* 配置，
    # 三个值在 backend/.env 填写（gitignored），任一为空即视觉识别不可用（analyze 降级 503）。
    vision_base_url: str = ""
    vision_api_key: str = ""
    vision_model_name: str = ""
    # 图片上传（B03）：本地磁盘存储，经 main.py 挂载的 /uploads 静态访问；
    # 目录在 backend/data/uploads（已 gitignore），按日期分子目录防单目录文件过多
    upload_dir: str = str(Path(__file__).resolve().parents[2] / "data" / "uploads")
    max_upload_mb: float = 5.0          # 单文件大小上限（PRD B03）
    hazard_no_prefix: str = "HZ"        # 隐患编号前缀，如 HZ20260813-0001
    # AI 出题参考文档文本截断上限（E02：上传培训手册/制度文件限定出题范围，纯文本不落盘）
    ref_doc_max_chars: int = 5000

    # ===== 模块二 AI 助手 RAG（M1 建库 / M2 检索 / M3 问答）=====
    # 本地模型/向量库均在实训根环境（仓库根），用绝对路径规避 transformers 5.14.1 相对路径 HFValidationError
    embed_model_dir: str = "D:/code/2026/7_8月实训/bge-large-zh"
    rerank_model_dir: str = "D:/code/2026/7_8月实训/bge-reranker-base"
    # Chroma 持久目录放在 backend/data/chroma_kb（新目录，勿指向实训根 PDF 语料的 chroma_db）
    chroma_persist_dir: str = str(Path(__file__).resolve().parents[2] / "data" / "chroma_kb")
    chroma_collection: str = "shudao_kb"
    # 检索参数（对齐 docs/RAG优化方案.md §0.2 全局参数契约，唯一真源）
    rag_vector_top_k: int = 50          # 向量路召回
    rag_bm25_top_k: int = 50            # BM25 路召回
    rag_rrf_k: int = 60                 # RRF 融合 K
    rag_fusion_top_k: int = 20          # RRF 融合后取前 N 进重排
    rag_rerank_top_n: int = 5           # 重排后进 LLM 的块数（含展开块）
    rag_conf_refuse: float = 0.30       # 归一化置信度 < 0.30 → 拒答
    rag_conf_conservative: float = 0.45  # < 0.45 → 保守模式；≥ → 全量
    # 向量余弦相似度绝对下限：RRF 纯排名融合对无关查询也会排个 top-1，相对峰值归一化
    # 无法识别「检索到但与问题无关」。top_vec_sim < 下限即拒答（防幻觉）。
    # 0.75 按评测集标定（data/calibrate_refusal.py，2026-08-13）：
    #   相关查询 top_vec_sim ∈ [0.818, 0.899]（n=6），无关 ∈ [0.641, 0.716]（n=8），
    #   两簇间空隙 [0.716, 0.818]，取中点 0.75 干净分离。0.30 对 bge 稠密向量
    #   （基线相似度 ~0.6-0.7）形同虚设，无关查询也全部 >0.30。
    rag_vec_sim_floor: float = 0.75
    rag_parent_split_chars: int = 400   # 条长超过该值才二次分块
    rag_child_min_chars: int = 100      # 子块最小字数
    rag_child_max_chars: int = 250      # 子块最大字数
    rag_max_rounds: int = 5             # 多轮上下文轮数
    # 问答流式（M3）
    rag_llm_semaphore: int = 8          # LLM 并发信号量（背压，防打满上游限流）
    rag_llm_max_tokens: int = 800       # 全量模式回答 max_tokens
    rag_llm_conservative_tokens: int = 300  # 保守模式回答 max_tokens（收紧，防过度发挥）
    rag_stream_ping_sec: float = 60.0   # SSE 保活阈值：LLM 静默超过该秒数发 ping

    model_config = SettingsConfigDict(
        env_file=(ENV_FILE,),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
