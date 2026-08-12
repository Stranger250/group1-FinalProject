"""法规语料库（BM25 内存直读）。

E02 AI 出题的检索层。技术决策（E02 一期）：
- 检索用 jieba 分词 + rank_bm25.BM25Okapi，全部条款一次性读入内存，不做向量库；
- 语料来源 crawler_output/ 下的 28 部法规 JSON（UTF-8），结构统一为
  `chapters[].{chapter, articles[].{no, content}}`，条号 no 存为 article_no，
  law_title 取文件顶层 title（已 strip）；
- 只有 content 非空、且无 parse_error（文件级 + 单条防御）的条款才入库。

对外契约（供其他模块 import）：
    LawCorpus(law_dir)                —— law_dir 目录内 *.json 为法规文件
    corpus.search(query, top_k, law_title) -> [{law_title, article_no, content, score}]
    corpus.law_titles                 —— 全部法规 title（去重、按名排序）
    load_corpus()                     —— lru_cache 单例，默认读 settings.law_json_dir
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 索引文件的文件名（统一扁平索引，不是法规本体，跳过）
_INDEX_FILE = "index.json"


def _repo_root() -> Path:
    """仓库根目录：本文件位于 backend/app/ai/law_corpus.py，上 3 级即仓库根。"""
    return Path(__file__).resolve().parents[3]


class LawCorpus:
    """内存语料库：启动时读入全部法规条款，构建 BM25 索引供检索。"""

    def __init__(self, law_dir: str | Path) -> None:
        self._law_dir = Path(law_dir)
        # 逐条条款记录，key 与契约一致：law_title / article_no / content
        self._articles: list[dict[str, str]] = []
        # 每条条款对应的 jieba 分词结果（与 _articles 一一对应），供 BM25 打分
        self._tokenized: list[list[str]] = []
        # 全部法规 title（去重在 law_titles 属性里做）
        self._titles: set[str] = set()
        # 全量语料的 BM25 索引
        self._bm25: BM25Okapi | None = None
        self._load()

    # ===== 构建 =====

    def _load(self) -> None:
        """读取 law_dir 下全部 *.json（跳过 index.json），构建条款表与 BM25 索引。"""
        if not self._law_dir.is_dir():
            logger.warning("法规目录不存在，语料为空：%s", self._law_dir)
            return
        # 排序保证加载顺序稳定（law_titles 排序在属性里再做一遍）
        for path in sorted(self._law_dir.glob("*.json")):
            if path.name == _INDEX_FILE:
                continue  # 扁平索引文件，非法规本体
            try:
                self._load_file(path)
            except (OSError, json.JSONDecodeError) as exc:  # noqa: PERF203
                # 单个文件异常不阻断整库加载
                logger.warning("跳过法规文件 %s：%s", path.name, exc)
        if self._articles:
            self._bm25 = BM25Okapi(self._tokenized)

    def _load_file(self, path: Path) -> None:
        """解析单个法规 JSON，把合法条款追加进条款表。"""
        with open(path, encoding="utf-8") as fp:
            doc = json.load(fp)
        # 文件级解析失败（parse_error 非空，如 null 则视为解析正常）→ 整篇不入库
        if doc.get("parse_error"):
            logger.warning("跳过 %s：文件级 parse_error=%r", path.name, doc["parse_error"])
            return
        title = (doc.get("title") or "").strip()
        if not title:
            logger.warning("跳过 %s：顶层 title 为空", path.name)
            return
        self._titles.add(title)
        for chapter in doc.get("chapters") or []:
            for article in chapter.get("articles") or []:
                content = (article.get("content") or "").strip()
                if not content:
                    continue  # 空内容条款不入库
                if article.get("parse_error"):
                    continue  # 防未来单条解析失败
                article_no = (article.get("no") or "").strip()
                self._articles.append(
                    {"law_title": title, "article_no": article_no, "content": content}
                )
                self._tokenized.append(self._tokenize(content))

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """jieba 精确模式分词，供 BM25 建索引与 query 打分。"""
        return [w for w in jieba.cut(text) if w.strip()]

    # ===== 检索 =====

    def search(
        self,
        query: str,
        top_k: int = 8,
        law_title: str | None = None,
    ) -> list[dict]:
        """BM25 检索全部条款，返回按 score 降序的 [{law_title, article_no, content, score}]。

        若 law_title 指定，仅在该法规内检索（title 精确匹配），命中即跨法规一并检索。
        score 为 0（或负，常见词 idf 为负）的条款视为无意义匹配，丢弃。
        """
        if not query or not query.strip() or self._bm25 is None:
            return []
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        if law_title is not None:
            # 限定单部法规：只对命中子集重新打分（idf 在法规内计算，排序更合理）
            return self._search_subset(query_tokens, law_title, top_k)
        # 全量打分 → 按分数降序取 top_k
        ranked = sorted(
            zip(range(len(scores)), scores), key=lambda pair: pair[1], reverse=True
        )
        results: list[dict] = []
        for idx, score in ranked:
            if score <= 0:
                break  # 已按降序，之后都是 0/负分，无需继续
            results.append({**self._articles[idx], "score": round(float(score), 4)})
            if len(results) >= top_k:
                break
        return results

    def _search_subset(
        self, query_tokens: list[str], law_title: str, top_k: int
    ) -> list[dict]:
        """在指定法规内检索：取该法规的条款下标，重建 BM25 后打分排序。"""
        indices = [
            i for i, article in enumerate(self._articles)
            if article["law_title"] == law_title
        ]
        if not indices:
            return []
        subset_bm25 = BM25Okapi([self._tokenized[i] for i in indices])
        scores = subset_bm25.get_scores(query_tokens)
        ranked = sorted(
            zip(indices, scores), key=lambda pair: pair[1], reverse=True
        )
        results: list[dict] = []
        for idx, score in ranked:
            if score <= 0:
                break
            results.append({**self._articles[idx], "score": round(float(score), 4)})
            if len(results) >= top_k:
                break
        return results

    # ===== 元数据 =====

    @property
    def law_titles(self) -> list[str]:
        """全部法规 title，去重、按名排序。"""
        return sorted(self._titles)


@lru_cache(maxsize=1)
def load_corpus() -> LawCorpus:
    """语料库单例（lru_cache，进程内只构建一次）。

    law_dir 默认取 settings.law_json_dir。配置值相对 backend 运行目录（默认
    ../crawler_output，即仓库根下的 crawler_output），这里以本模块所在 backend
    目录为基准解析为仓库根绝对路径，避免依赖 cwd。
    """
    setting = (get_settings().law_json_dir or "").strip() or "../crawler_output"
    law_dir = Path(setting)
    if not law_dir.is_absolute():
        # parents[2] = backend（law_corpus.py 位于 backend/app/ai/）
        law_dir = (Path(__file__).resolve().parents[2] / law_dir).resolve()
    return LawCorpus(law_dir)
