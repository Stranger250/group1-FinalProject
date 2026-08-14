"""M1 知识库构建 CLI + 全量验收断言。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/build_knowledge_base.py [--force] [--no-mysql] [--no-chroma]
退出码 0 = 全部断言通过。

验收断言（对照 docs/RAG优化方案.md §0 / docs/数据格式与建库注意事项.md §5）：
  文档数=28、章=199、条=2087、全文=303734 字；引用解析覆盖率 ≥90%；
  Chroma 计数=分块总数且空间 cosine；MySQL docs=28、chunks=分块总数；
  vector_id↔chunk_id 全量对应；>400 字子块父指针回指正确；抽样 20 条 Recall@5 粗查。

幂等：--force 先删 MySQL 两表 + Chroma delete_collection，二次运行不翻倍。
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# backend/scripts/ → backend/ 入 sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BACKEND_DIR)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("build_kb")

# 盘点审计真源（docs/_rag_data_audit.json totals）
EXPECTED = {"files": 28, "chapters": 199, "articles": 2087, "chars": 303734}
EXPECTED_REFS = 172

FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> bool:
    if not cond:
        FAILURES.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""))
    return cond


def main() -> None:
    from app.core.config import get_settings
    from app.rag.build.loader import run_build
    from app.rag.embedder import get_embedder

    settings = get_settings()
    parser = argparse.ArgumentParser(description="蜀道知识库构建")
    parser.add_argument("--force", action="store_true", help="重建：清空 MySQL 两表 + Chroma collection")
    parser.add_argument("--data-dir", default="", help="法规 JSON 目录（默认 settings.law_json_dir）")
    parser.add_argument("--no-mysql", action="store_true", help="跳过 MySQL 写入")
    parser.add_argument("--no-chroma", action="store_true", help="跳过 Chroma 写入（仅跑清洗/解析/引用）")
    args = parser.parse_args()

    data_dir = args.data_dir or os.path.normpath(os.path.join(BACKEND_DIR, settings.law_json_dir))
    if not os.path.isdir(data_dir):
        logger.error("数据目录不存在: %s", data_dir)
        sys.exit(2)

    print(f"== 建库（force={args.force} mysql={not args.no_mysql} chroma={not args.no_chroma}）==")
    print(f"数据目录: {data_dir}")
    stats, blocks_by_doc = run_build(
        data_dir=data_dir, force=args.force,
        write_mysql=not args.no_mysql, write_chroma=not args.no_chroma,
    )

    # ---------- 断言 ----------
    total_blocks = stats.parent_blocks + stats.child_blocks
    print(f"\n== 统计 ==")
    print(f"  文件 {stats.files} | 章 {stats.chapters} | 条 {stats.articles} | 全文 {stats.full_chars} 字")
    print(f"  父块 {stats.parent_blocks} + 子块 {stats.child_blocks} = {total_blocks}")
    print(f"  引用 {stats.ref_resolved}/{stats.ref_found} 解析率 {stats.ref_rate:.1%}")
    if stats.stale_flagged:
        print(f"  ⚠ 过期待人工核实: {', '.join(stats.stale_flagged)}")
    if stats.ref_unresolved:
        print(f"  ⚠ 未解析引用 {len(stats.ref_unresolved)} 处:")
        for u in stats.ref_unresolved[:10]:
            print(f"      {u['doc_id']} {u['article_no']} → {u['target']} ({u['reason']})")

    print("\n== 结构断言（对照盘点审计）==")
    ok("文档数 = 28", stats.files == EXPECTED["files"], str(stats.files))
    ok("章 = 199", stats.chapters == EXPECTED["chapters"], str(stats.chapters))
    ok("条 = 2087", stats.articles == EXPECTED["articles"], str(stats.articles))
    ok("全文 = 303734 字", stats.full_chars == EXPECTED["chars"], str(stats.full_chars))
    ok(f"引用解析率 ≥90%（{EXPECTED_REFS} 处）", stats.ref_rate >= 0.90, f"{stats.ref_rate:.1%}")
    # 修复（核对发现）：引用总数 172 此前只出现在提示文案、未被真正断言（found=0 时 rate=1.0 会误判 PASS）
    ok(f"引用总数 = {EXPECTED_REFS}", stats.ref_found == EXPECTED_REFS,
       f"found={stats.ref_found} resolved={stats.ref_resolved}")

    if not args.no_chroma:
        import subprocess

        import chromadb

        # 新鲜进程持久化检查（放最前）：chromadb 1.5.x Rust 后端 close() 落盘若被吞
        # （幽灵路径 bug，见 PR #5923），会留下 index_metadata.pickle 而无 .bin。
        # 同进程读是内存态，掩盖问题；先起子进程真实验证「重启后仍可读」，
        # 失败即干净 FAIL（而非在下方 in-process col.count() 处直接抛错）。
        _code = (
            "import sys, chromadb\n"
            "client = chromadb.PersistentClient(path=sys.argv[1])\n"
            "col = client.get_or_create_collection(sys.argv[2])\n"
            "n = col.count()\n"
            "res = col.query(query_embeddings=[[1.0]+[0.0]*1023], n_results=2, include=[])\n"
            "client.close()\n"
            "print(n, len(res['ids'][0]))\n"
        )
        p = subprocess.run(
            [sys.executable, "-c", _code, settings.chroma_persist_dir, settings.chroma_collection],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        fresh_ok = p.returncode == 0 and p.stdout.strip().startswith(str(total_blocks))
        ok(f"新鲜进程可读（count={total_blocks} + query）", fresh_ok,
           f"rc={p.returncode} out={p.stdout.strip()!r} err={p.stderr.strip()[:160]!r}")

        # 落盘检查通过后再做进程内断言（此时 .bin 已就位，同进程读不会再崩）
        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        col = client.get_or_create_collection(settings.chroma_collection)
        chroma_ids = set(col.get(include=[])["ids"]) if col.count() else set()
        print("\n== Chroma 断言 ==")
        ok("Chroma 计数 = 分块总数", stats.chroma_count == total_blocks, f"{stats.chroma_count} vs {total_blocks}")
        ok("空间 = cosine", col.metadata.get("hnsw:space") == "cosine", str(col.metadata.get("hnsw:space")))

        # 抽样 20 条 Recall@5 粗查（向量路前缀召回；全链路在 M5 端到端测）
        parents = [b for b in (b for bs in blocks_by_doc.values() for b in bs) if b.is_parent and b.article_no]
        n = min(20, len(parents))
        step = (len(parents) - 1) / (n - 1) if n > 1 else 0
        idxs = sorted({int(round(i * step)) for i in range(n)})
        embedder = get_embedder()
        hits = 0
        misses: list[str] = []
        for i in idxs:
            b = parents[i]
            vec = embedder.embed_query(b.content[:40])
            res = col.query(query_embeddings=[vec], n_results=5, include=["metadatas"])
            got = res["ids"][0]
            if b.chunk_id in got:
                hits += 1
            else:
                misses.append(b.chunk_id)
        ok(f"抽样 {n} 条 Recall@5 ≥ 15", hits >= max(15, int(n * 0.75)), f"{hits}/{n}")
        if misses:
            print(f"      miss 示例: {misses[:5]}")
        client.close()  # 进程内后台 compactor 落盘后释放文件锁

    if not args.no_mysql:
        from sqlalchemy import create_engine, text

        eng = create_engine(settings.database_url)
        with eng.connect() as conn:
            docs_n = conn.execute(text("SELECT COUNT(*) FROM knowledge_document")).scalar()
            chunks_n = conn.execute(text("SELECT COUNT(*) FROM knowledge_chunk")).scalar()
            vector_ids = set(r[0] for r in conn.execute(text("SELECT vector_id FROM knowledge_chunk")))
        print("\n== MySQL 断言 ==")
        ok("knowledge_document = 28", docs_n == EXPECTED["files"], str(docs_n))
        ok("knowledge_chunk = 分块总数", chunks_n == total_blocks, f"{chunks_n} vs {total_blocks}")
        if not args.no_chroma:
            ok("vector_id ↔ Chroma id 全量对应", vector_ids == chroma_ids,
               f"mysql={len(vector_ids)} chroma={len(chroma_ids)}")

    # >400 字子块父指针回指
    print("\n== 子块父指针断言 ==")
    by_chunk = {b.chunk_id: b for bs in blocks_by_doc.values() for b in bs}
    bad_parent = []
    for b in (b for bs in blocks_by_doc.values() for b in bs):
        if not b.is_parent:
            p = by_chunk.get(b.parent_id)
            if not p or p.db_chunk_id != b.parent_db_chunk_id:
                bad_parent.append(b.chunk_id)
    ok(f"子块父指针全量回指正确（子块 {stats.child_blocks} 个）", not bad_parent,
       f"异常 {len(bad_parent)}: {bad_parent[:3]}")
    # 每条父块 db 主键齐全（仅在写 MySQL 后有效）
    if not args.no_mysql:
        missing_db = [b.chunk_id for b in by_chunk.values()
                      if b.db_chunk_id is None or b.db_doc_id is None or b.parent_db_chunk_id is None]
        ok("全部块 db_doc_id/db_chunk_id/parent_db_chunk_id 已回填", not missing_db,
           f"缺失 {len(missing_db)}: {missing_db[:3]}")

    print(f"\n===== 建库完成：{len(FAILURES)} 个失败 =====")
    if FAILURES:
        print("失败项：", "；".join(FAILURES))
        sys.exit(1)
    print(f"耗时：MySQL {stats.db_time_s:.1f}s / 嵌入+Chroma {stats.embedding_time_s:.1f}s")
    print("全部断言通过 ✅")


if __name__ == "__main__":
    main()
