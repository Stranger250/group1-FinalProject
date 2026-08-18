"""混合检索器（RAG 方案 §2：向量 Top-50 + BM25 Top-50 → RRF K=60 → 交叉引用展开 → bge-reranker → Top-5）。

流水线（契约 §0.2 / §2.6 / §0.5）：
  ① 向量路：bge-large-zh embed → Chroma query(n=50, access_level where)
  ② 关键词路：jieba + BM25 Top-50（改写 query 与原文双路，score 取 max）
  ③ RRF K=60 融合 → Top-20
  ④ 交叉引用展开：Top-3 含 ref_out → 查回父块（expanded=true，不二次展开）
  ⑤ reranker 父块粒度 Top-(20+展开) → Top-5
  ⑥ 置信度：RRF 归一化（相对理论峰值 2/(K+1)）→ mode（refuse/conservative/full）
块从 Chroma metadata 一次性索引（单一数据源），BM25 同源构建；仅启动时加载。

置信度说明：契约写 min-max 归一化，但单候选时 min==max→0.0 会把强命中误判拒答。
实现采用「相对理论峰值」归一化（top_rrf × (K+1)/2 截断到 [0,1]），分布照常打日志，
阈值上线前按 §5.6 评测集联合标定。normalize_rrf（min-max）保留在 confidence.py 供日志用。
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field

import chromadb

from ..core.config import get_settings
from .bm25 import BM25Index
from .citations import RetrievedBlock
from .confidence import classify
from .embedder import get_embedder
from .rag_config import RAGParams
from .reranker import get_reranker

logger = logging.getLogger("rag.retriever")

# 权限矩阵（契约 §7.2）：员工=公开；管理员=公开+内部。MVP 全公开。
ACCESS_EMPLOYEE = ("公开",)
ACCESS_ADMIN = ("公开", "内部")


def _jlist(v) -> list[str]:
    """metadata 里 JSON 编码的列表字段解码（ref_out/domain_tags）。"""
    if not v:
        return []
    try:
        parsed = json.loads(v)
        return list(parsed) if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _tier_of(meta: dict) -> str:
    """O7 回答依据行政层级：national 国家级 / province 省级 / lower 更低级（企业规范等）。

    判定口径（PRD-V2 O7）：企业级语料（company/sop/plan/case）→ lower；
    region=四川 → province；其余（国家法律/行政法规/部门规章）→ national。
    """
    doc_type = meta.get("doc_type") or ""
    if doc_type in ("company", "sop", "plan", "case"):
        return "lower"
    if (meta.get("region") or "") == "四川":
        return "province"
    return "national"


@dataclass
class SearchResult:
    blocks: list[RetrievedBlock] = field(default_factory=list)
    mode: str = "refuse"
    confidence: float = 0.0
    top_vec_sim: float = 0.0  # 向量路 top-1 余弦相似度（绝对值，拒答下限信号）
    rrf_pool: list[float] = field(default_factory=list)  # 融合池 RRF 原始分（日志）
    vector_hits: int = 0
    bm25_hits: int = 0
    title_hits: int = 0  # RAG2.0#9：标题路命中文档数


class HybridRetriever:
    def __init__(self) -> None:
        settings = get_settings()
        self._params = RAGParams.from_settings()
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        try:
            self._col = self._client.get_or_create_collection(settings.chroma_collection)
            self._load_index()
        except Exception:
            # Chroma 损坏/不可读时仍要释放 client，否则遗弃的 PersistentClient
            # 会持有 sqlite 句柄，干扰后续 build 的 compactor 落盘（幽灵路径 bug 关联）。
            self._client.close()
            raise

    # ---------- 索引（一次性） ----------

    def reload(self) -> None:
        """O10 文档停用/删除/上传后重载索引（块集合变化即时生效）。

        重载期间其他线程可能正在 search —— 用模块级锁串行化 _load_index，
        并把旧索引对象原地替换（search 持有的是 self 属性引用，替换后自然读到新索引）。
        """
        with _retriever_lock:
            data = self._col.get(include=["documents", "metadatas"])
            if data["ids"]:
                self._load_index()

    def _load_index(self) -> None:
        data = self._col.get(include=["documents", "metadatas"])
        if not data["ids"]:
            raise RuntimeError("Chroma 集合为空：先跑 scripts/build_knowledge_base.py 建库")
        self._meta_by_id: dict[str, dict] = {
            cid: meta for cid, meta in zip(data["ids"], data["metadatas"])
        }
        access_by_id = {cid: meta.get("access_level", "公开") for cid, meta in self._meta_by_id.items()}
        docs = [{"chunk_id": cid, "content": txt} for cid, txt in zip(data["ids"], data["documents"])]
        self._bm25 = BM25Index(docs, access_by_id=access_by_id)

        # RAG2.0#9：标题路 BM25——每篇文档取一个父块（或首个块）用其标题建索引。
        # 标题实体词（如「包钢稀土」「国家总体预案」）在正文索引中命中不到，
        # 单独标题索引作为第三路参与 RRF，IDF 保证通用词（安全/生产）不产生干扰。
        title_docs: list[dict] = []
        seen_doc: set[str] = set()
        for cid, meta in zip(data["ids"], data["metadatas"]):
            doc_id = meta.get("doc_id") or ""
            title = (meta.get("title") or "").strip()
            if not title or doc_id in seen_doc:
                continue
            seen_doc.add(doc_id)
            title_docs.append({"chunk_id": cid, "content": title})
        self._bm25_title = BM25Index(title_docs, access_by_id=access_by_id)

        # 子块 → 父块回溯映射（build 保证：父块 parent_chunk_id=自身，子块=其父块）
        self._parent_by_chunk: dict[str, str] = {
            cid: (meta.get("parent_chunk_id") or cid) for cid, meta in self._meta_by_id.items()
        }

        # (doc_id, article_no) → 父块 chunk_id（查看原文 / 引用展开精确查回）
        self._article_index: dict[tuple[str, str], str] = {}
        for cid, meta in self._meta_by_id.items():
            if meta.get("is_parent") and meta.get("article_no"):
                self._article_index[(meta["doc_id"], meta["article_no"])] = cid

    # ---------- 主检索 ----------

    def search(self, query: str, kw_queries: list[str] | None = None,
               access_levels: tuple[str, ...] = ACCESS_EMPLOYEE) -> SearchResult:
        p = self._params
        result = SearchResult()

        # ① 向量路（cosine 空间 distance = 1 - 余弦相似度；顺带取 distances 拿绝对相似度）
        qvec = get_embedder().embed_query(query)
        where = {"access_level": {"$in": list(access_levels)}}
        try:
            res = self._col.query(
                query_embeddings=[qvec], n_results=p.vector_top_k, where=where,
                include=["metadatas", "distances"],
            )
        except Exception:
            res = self._col.query(
                query_embeddings=[qvec], n_results=p.vector_top_k,
                include=["metadatas", "distances"],
            )
        raw_ids = res["ids"][0] if res["ids"] else []
        raw_dists = res["distances"][0] if res.get("distances") and res["distances"] else []
        vec_pairs = [
            (cid, dist) for cid, dist in zip(raw_ids, raw_dists)
            if cid in self._meta_by_id
            and self._meta_by_id[cid].get("access_level", "公开") in access_levels
        ]
        vector_ids = [cid for cid, _ in vec_pairs]
        result.vector_hits = len(vector_ids)
        result.top_vec_sim = round(1.0 - vec_pairs[0][1], 4) if vec_pairs else 0.0

        # ② BM25 路（原文 + 改写后双 query，score 取 max）
        bm25_scores: dict[str, float] = {}
        for q in [query] + list(kw_queries or []):
            for cid, sc in self._bm25.search(q, p.bm25_top_k, access_levels):
                bm25_scores[cid] = max(bm25_scores.get(cid, 0.0), sc)
        bm25_ids = [cid for cid, _ in sorted(bm25_scores.items(), key=lambda x: x[1], reverse=True)]
        result.bm25_hits = len(bm25_ids)

        # ②b 标题路（RAG2.0#9）：标题 BM25 命中文档 → 其全部父块加入融合池（文档级信号）
        title_hit_docs: set[str] = set()
        for q in [query] + list(kw_queries or []):
            for cid, _sc in self._bm25_title.search(q, p.bm25_top_k, access_levels):
                title_hit_docs.add(cid)  # cid 是该文档的代表块
        title_ids: list[str] = []
        if title_hit_docs:
            # 代表块 → 该文档全部父块
            doc_of: dict[str, str] = {cid: self._meta_by_id[cid].get("doc_id", "") for cid in title_hit_docs}
            for cid, meta in self._meta_by_id.items():
                if meta.get("is_parent") and meta.get("doc_id") in doc_of.values():
                    title_ids.append(cid)
        result.title_hits = len(title_hit_docs)

        # ③ RRF 融合（向量 + 正文 BM25 + 标题 BM25 三路）
        rrf: dict[str, float] = {}
        for rank, cid in enumerate(vector_ids, start=1):
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (p.rrf_k + rank)
        for rank, cid in enumerate(bm25_ids, start=1):
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (p.rrf_k + rank)
        for rank, cid in enumerate(title_ids, start=1):
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (p.rrf_k + rank)
        fused = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:p.fusion_top_k]
        if not fused:
            return result  # 检索为空 → refuse，不调 LLM

        # 父块粒度聚合（子块回溯父块，RRF 取 max）+ 记录融合池原始分
        parent_rrf: dict[str, float] = {}
        for cid, sc in fused:
            parent = self._parent_by_chunk.get(cid, cid)
            parent_rrf[parent] = max(parent_rrf.get(parent, 0.0), sc)
        result.rrf_pool = sorted(parent_rrf.values(), reverse=True)
        # O7 依据分层：行政层级加权（国家优先）——国家级 ×1.10、省级 ×1.05、更低级(企业语料) ×1.00，
        # 在父块排序与置信度前生效，让国家级依据在同类相关度下更靠前（同层内仍按 RRF）。
        tier_bonus = {"national": 1.10, "province": 1.05, "lower": 1.00}
        parent_candidates = sorted(
            parent_rrf.items(),
            key=lambda x: x[1] * tier_bonus.get(_tier_of(self._meta_by_id.get(x[0], {})), 1.0),
            reverse=True,
        )

        # ④ 交叉引用展开（Top-3 含 ref_out → 查回被引父块，expanded=true，不二次展开）
        expanded_ids: list[str] = []
        candidate_ids = {cid for cid, _ in parent_candidates}
        for cid, _ in parent_candidates[:3]:
            meta = self._meta_by_id[cid]
            for tgt in _jlist(meta.get("ref_out"))[:3]:
                if tgt in self._meta_by_id and tgt not in candidate_ids and tgt not in expanded_ids:
                    expanded_ids.append(tgt)

        # ⑤ reranker 父块粒度 Top-N
        pool_ids = [cid for cid, _ in parent_candidates] + expanded_ids
        # RAG2.0#10：rerank 输入注入标题（「{title}：{content}」）——cross-encoder 感知文档实体名，
        # 包钢稀土类查询此前 rerank 只看正文，文档级实体信号丢失（标题路已进融合池仍被排掉）。
        pairs = [
            (cid, f"{self._meta_by_id[cid].get('title', '')}：{self._meta_by_id[cid]['content']}")
            for cid in pool_ids
        ]
        reranked = get_reranker().rerank(query, pairs, top_n=p.rerank_top_n)
        # O7 国家优先：rerank 分数同级时按层级 bonus 微调顺序（入选集合不变，仅排序）
        # rerank 返回 (chunk_id, content, score)
        reranked.sort(
            key=lambda t: t[2] * tier_bonus.get(_tier_of(self._meta_by_id.get(t[0], {})), 1.0),
            reverse=True,
        )
        top_ids = [cid for cid, _, _ in reranked]

        # ⑥ 置信度：相对理论峰值归一化 → mode（分布式日志）
        if parent_rrf:
            top_rrf = parent_rrf[parent_candidates[0][0]]
            confidence = min(1.0, top_rrf * (p.rrf_k + 1) / 2.0)
        else:
            confidence = 0.0
        mode = classify(confidence, p.conf_refuse, p.conf_conservative)
        result.confidence = confidence
        result.mode = mode
        logger.info(
            "检索 mode=%s conf=%.3f sim=%.3f vec=%d bm25=%d pool=%d rrf_pool=%s",
            mode, confidence, result.top_vec_sim, result.vector_hits, result.bm25_hits, len(pool_ids),
            [round(x, 4) for x in result.rrf_pool[:5]],
        )

        # 组装返回块：rrf_score 用「父块聚合分」（parent_rrf，子块回溯取 max），
        # 使被二次分块的长条文父块也有真实融合分（此前用子块级 rrf.get(cid)，
        # 对拆分条恒为 0 → 相关度条/落库分为空）。展开块不在 parent_rrf，得 0（展示走 floor）。
        result.blocks = [self._to_block(cid, parent_rrf.get(cid, 0.0), confidence, cid in expanded_ids)
                         for cid in top_ids if cid in self._meta_by_id]
        return result

    # ---------- 查看原文 ----------

    def get_article(self, doc_id: str, article_no: str,
                    access_levels: tuple[str, ...] = ACCESS_EMPLOYEE) -> RetrievedBlock | None:
        """doc_id+article_no → 父块全文（重复条号取首个，MVP 口径）。"""
        cid = self._article_index.get((doc_id, article_no))
        if not cid or cid not in self._meta_by_id:
            return None
        if self._meta_by_id[cid].get("access_level", "公开") not in access_levels:
            return None
        return self._to_block(cid, 0.0, 0.0, False)

    # ---------- 组装 ----------

    def _to_block(self, cid: str, rrf_score: float, confidence: float, expanded: bool) -> RetrievedBlock:
        m = self._meta_by_id[cid]
        return RetrievedBlock(
            chunk_id=cid,
            doc_id=m.get("doc_id", ""),
            title=m.get("title", ""),
            doc_no=m.get("doc_no", ""),
            category=m.get("category", ""),
            doc_level=int(m.get("doc_level") or 3),
            region=m.get("region", ""),
            tier=_tier_of(m),  # O7 行政层级（national/province/lower）
            chapter=m.get("chapter", ""),
            article_no=m.get("article_no", ""),
            content=m.get("content", ""),
            is_parent=bool(m.get("is_parent")),
            parent_chunk_id=m.get("parent_chunk_id", cid),
            status=m.get("status", ""),
            publish_date=m.get("publish_date", ""),
            effective_date=m.get("effective_date", ""),
            version=m.get("version", ""),
            source_url=m.get("source_url", ""),
            ref_out=_jlist(m.get("ref_out")),
            domain_tags=_jlist(m.get("domain_tags")),
            difficulty=m.get("difficulty", "easy"),
            access_level=m.get("access_level", "公开"),
            db_doc_id=int(m.get("db_doc_id") or 0),
            db_chunk_id=int(m.get("db_chunk_id") or 0),
            parent_db_chunk_id=int(m.get("parent_db_chunk_id") or 0),
            rrf_score=rrf_score,
            confidence=confidence,
            expanded=expanded,
        )


_retriever: HybridRetriever | None = None
_retriever_lock = threading.Lock()


def get_retriever() -> HybridRetriever:
    """单例；加载 2544 块索引 + BM25 建倒排较慢，由 main.py lifespan 预热。"""
    global _retriever
    with _retriever_lock:
        if _retriever is None:
            _retriever = HybridRetriever()
        return _retriever
