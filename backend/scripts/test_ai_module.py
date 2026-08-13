"""模块二 AI 智能助手（A01-A07）端到端测试。

前置：后端已在 8000 端口运行（uvicorn app.main:app --reload），
知识库已建（build_knowledge_base.py 全绿），MySQL shudao 库就绪。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_ai_module.py

覆盖：
  A01 SSE 事件序 meta→delta→done、citations 与 done 一致、synthetic=true
  A01 拒答不调 LLM（无相关检索 → 固定话术 + 空引用）
  A01 敏感词预检 400（不进检索/LLM）
  A01 多轮指代消解（含"它"→ 改写标记 rewritten_used）
  A02 会话 CRUD + 级联删除（message_source→message→conversation 清空）
  A02 他人会话 404 掩码（防枚举）
  A03 查看原文（父块全文）、引用落库 join 回 knowledge_* 表
  A04 快捷提问非空
  A07 反馈幂等（1→1→0 清除）
  鉴权 401 / 并发冒烟（2 线程不同会话）
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://127.0.0.1:8000/api/v1"
FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> bool:
    if not cond:
        FAILURES.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""))
    return cond


def new_client() -> httpx.Client:
    return httpx.Client(base_url=BASE, trust_env=False, timeout=120)


def login(client: httpx.Client, username: str, password: str) -> str:
    r = client.post("/auth/login", data={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["data"]["access_token"]


def register_or_login(client: httpx.Client, username: str, password: str, name: str) -> str:
    r = client.post("/auth/register", json={"username": username, "password": password, "name": name})
    if r.status_code == 200:
        return login(client, username, password)
    return login(client, username, password)


def sse_chat(client: httpx.Client, token: str, body: dict) -> tuple[int, list[dict]]:
    """POST /ai/chat，解析 SSE 块为 [{event, data}]。非 2xx 时 events 为空。"""
    events: list[dict] = []
    buf: list[str] = []
    status = 0
    with client.stream(
        "POST", "/ai/chat", json=body,
        headers={"Authorization": f"Bearer {token}"},
    ) as r:
        status = r.status_code
        for line in r.iter_lines():
            if line == "":
                if buf:
                    ev: dict = {}
                    for l in buf:
                        if l.startswith("event: "):
                            ev["event"] = l[len("event: "):]
                        elif l.startswith("data: "):
                            ev["data"] = json.loads(l[len("data: "):])
                    events.append(ev)
                    buf = []
            else:
                buf.append(line)
    return status, events


def events_summary(events: list[dict]) -> str:
    return "->".join(e.get("event", "?") for e in events)


def main() -> None:
    c = new_client()
    tok1 = register_or_login(c, "ai_chat_t1", "123456", "AI测试一")
    tok2 = register_or_login(c, "ai_chat_t2", "123456", "AI测试二")
    h1 = {"Authorization": f"Bearer {tok1}"}
    h2 = {"Authorization": f"Bearer {tok2}"}

    print("\n== T1 鉴权 & 快捷提问 ==")
    r = c.post("/ai/chat", json={"message": "你好"})
    ok("未登录 401", r.status_code == 401, f"status={r.status_code}")
    r = c.get("/ai/quick-questions", headers=h1)
    qq = r.json()["data"]
    ok("A04 快捷提问非空", r.status_code == 200 and len(qq) >= 10, f"n={len(qq)}")
    ok("快捷提问含 category/question", all("category" in q and "question" in q for q in qq))

    print("\n== T2 A01 首问 SSE 事件序（建会话+自动标题）==")
    status, ev = sse_chat(c, tok1, {"message": "安全生产法对生产经营单位主要负责人的安全生产职责是怎么规定的？"})
    ok("首问 200", status == 200, f"status={status}")
    seq = [e["event"] for e in ev]
    ok("事件序 meta→delta→done（首尾）", seq and seq[0] == "meta" and seq[-1] == "done",
       f"seq={events_summary(ev)}")
    meta = ev[0]["data"]
    conv_id = meta["conversation_id"]
    ok("meta 含引用/模式/改写标记", all(k in meta for k in
       ("conversation_id", "mode", "confidence", "citations", "rewritten_used")))
    ok("首问改写标记 False", meta["rewritten_used"] is False)
    mode = meta["mode"]
    citations = meta["citations"]
    done = ev[-1]["data"]
    answer_id = done["answer_id"]
    ok("done synthetic=true", done.get("synthetic") is True)
    ok("done 含引用且与 meta 一致", done.get("citations") == citations,
       f"citations={len(citations)}")
    ok("done 含 grounding_score", "grounding_score" in done)
    ok("首问命中知识库（非 refuse）", mode in ("full", "conservative"), f"mode={mode}")
    if mode == "refuse":
        # 职责类问题在 28 部法规中必有对应条文，拒答说明检索链路异常
        print(f"\n===== 首问 mode=refuse：{len(FAILURES)} 个失败 =====")
        sys.exit(1)
    ok("delta 有增量文本", any("text" in e["data"] and e["data"]["text"] for e in ev[1:-1]))
    ok("full/conservative 引用非空", len(citations) > 0, f"n={len(citations)}")

    # 会话列表：首问自动标题 = 问题前 20 字 + …
    r = c.get("/ai/conversations", headers=h1)
    convs = r.json()["data"]["items"]
    mine = next(x for x in convs if x["id"] == conv_id)
    ok("A02 首问自动标题（截断）", mine["title"].startswith("安全生产法对生产经营单位主要负责人的安"), mine["title"])

    print("\n== T3 A03 引用落库 join 回 knowledge_* 表 ==")
    from sqlalchemy import create_engine, text
    from app.core.config import get_settings
    eng = create_engine(get_settings().database_url)
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT s.id, s.document_id, s.chunk_id, s.document_name, "
            "k.vector_id, d.name AS doc_name "
            "FROM message_source s "
            "JOIN knowledge_chunk k ON k.id = s.chunk_id "
            "JOIN knowledge_document d ON d.id = s.document_id "
            "WHERE s.message_id = :mid LIMIT 5"
        ), {"mid": answer_id}).fetchall()
    ok("message_source 可 join 回 knowledge_chunk/document", len(rows) == len(citations),
       f"join={len(rows)} citations={len(citations)}")
    if rows:
        r0 = rows[0]
        ok("引用 document_name 非空", bool(r0.document_name) and r0.document_name == r0.doc_name,
           f"{r0.document_name} / {r0.doc_name}")
        # 引用卡片 chunk_id = Chroma chunk_id = 落库切片 vector_id（三者一致性）
        with eng.connect() as conn2:
            vid = conn2.execute(text(
                "SELECT vector_id FROM knowledge_chunk WHERE id = :cid"),
                {"cid": r0.chunk_id}).scalar()
        ok("引用卡片 chunk_id 对应知识库切片", vid == citations[0]["chunk_id"],
           f"vid={vid} cite={citations[0]['chunk_id']}")

    print("\n== T4 A03 查看原文 ==")
    src = citations[0]
    r = c.get("/ai/article", params={"doc_id": src["doc_id"], "article_no": src["article_no"]}, headers=h1)
    art = r.json()["data"]
    ok("查看原文 200 含条文", r.status_code == 200 and art and art.get("article_no") == src["article_no"],
       f"status={r.status_code}")
    ok("原文含出处字段", all(k in art for k in ("title", "doc_no", "category", "region", "content", "source_url")))

    print("\n== T5 A07 反馈幂等 ==")
    r = c.post(f"/ai/feedback/{answer_id}", json={"value": 1}, headers=h1)
    ok("反馈 1 成功", r.status_code == 200)
    r = c.post(f"/ai/feedback/{answer_id}", json={"value": 1}, headers=h1)
    ok("反馈重复幂等", r.status_code == 200)
    r = c.get(f"/ai/conversations/{conv_id}/messages", headers=h1)
    msgs = r.json()["data"]
    ai_msg = next(m for m in msgs if m["id"] == answer_id)
    ok("反馈值=1 已落库", ai_msg["feedback"] == 1, f"feedback={ai_msg['feedback']}")
    r = c.post(f"/ai/feedback/{answer_id}", json={"value": 0}, headers=h1)
    r = c.get(f"/ai/conversations/{conv_id}/messages", headers=h1)
    ai_msg = next(m for m in r.json()["data"] if m["id"] == answer_id)
    ok("反馈 0 清除", ai_msg["feedback"] == 0)

    print("\n== T6 A01 多轮指代消解 + 落库计数 ==")
    turns = [
        "它的第一条立法目的是什么？",          # 含"它" → 改写
        "那么从业人员有哪些安全生产权利？",
        "如何配发？",                          # ≤6 字（"如何配发？"=5 字），轮次≥2 → 改写
        "主要负责人的职责有哪些？",
    ]
    rewritten_flags = []
    for q in turns:
        status, ev = sse_chat(c, tok1, {"conversation_id": conv_id, "message": q})
        ok(f"多轮[{q[:12]}…] 200 且 done", status == 200 and ev and ev[-1]["event"] == "done",
           f"status={status}")
        meta = ev[0]["data"]
        rewritten_flags.append(meta["rewritten_used"])
    ok("含'它'触发改写", rewritten_flags[0] is True, f"flags={rewritten_flags}")
    ok("过短(轮次≥2)触发改写", rewritten_flags[2] is True, f"flags={rewritten_flags}")
    r = c.get(f"/ai/conversations/{conv_id}/messages", headers=h1)
    msgs = r.json()["data"]
    user_rows = [m for m in msgs if m["role"] == "user"]
    asst_rows = [m for m in msgs if m["role"] == "assistant"]
    ok("落库 user 行=5 条（首问+4 多轮）", len(user_rows) == 5, f"user={len(user_rows)}")
    ok("落库 assistant 行=5 条", len(asst_rows) == 5, f"asst={len(asst_rows)}")
    ok("assistant 行内联 sources", all(m["sources"] for m in asst_rows if m["status"] == "SUCCESS"))

    print("\n== T7 A01 拒答（无相关检索，不调 LLM）==")
    status, ev = sse_chat(c, tok1, {"conversation_id": conv_id, "message": "昨天晚上的足球比赛结果如何"})
    ok("拒答 200", status == 200, f"status={status}")
    seq = [e["event"] for e in ev]
    ok("拒答事件序 meta→delta→done", seq == ["meta", "delta", "done"], f"seq={seq}")
    meta = ev[0]["data"]
    done = ev[-1]["data"]
    ok("拒答引用为空", meta["citations"] == [] and done["answer_id"] == 0)
    ok("拒答话术为固定文案", "没有" in ev[1]["data"]["text"], ev[1]["data"]["text"][:30])
    ok("拒答 synthetic=true", done.get("synthetic") is True)

    print("\n== T8 敏感词预检 400 ==")
    status, ev = sse_chat(c, tok1, {"conversation_id": conv_id, "message": "如何购买枪支"})
    ok("命中敏感词 400", status == 400 and not ev, f"status={status}")
    r = c.post("/ai/chat", json={"conversation_id": conv_id, "message": "如何购买枪支"}, headers=h1)
    ok("非流式同样 400 且不进检索", r.status_code == 400 and "敏感词" in r.json()["message"])

    print("\n== T9 A02 他人会话 404 掩码 ==")
    r = c.get(f"/ai/conversations/{conv_id}/messages", headers=h2)
    ok("他人消息 404", r.status_code == 404)
    r = c.delete(f"/ai/conversations/{conv_id}", headers=h2)
    ok("他人删除 404", r.status_code == 404)
    r = c.get(f"/ai/source/{answer_id}", headers=h2)
    ok("他人引用 404", r.status_code == 404)

    print("\n== T10 A02 会话 CRUD + 级联删除 ==")
    r = c.put(f"/ai/conversations/{conv_id}", json={"title": "重命名-测试"}, headers=h1)
    ok("重命名 200", r.status_code == 200 and r.json()["data"]["title"] == "重命名-测试")
    r = c.post("/ai/conversations", json={"title": "独立会话"}, headers=h1)
    cid2 = r.json()["data"]["id"]
    r = c.delete(f"/ai/conversations/{cid2}", headers=h1)
    ok("删除 200", r.status_code == 200)
    r = c.get(f"/ai/conversations/{cid2}/messages", headers=h1)
    ok("删除后访问 404", r.status_code == 404)
    r = c.delete(f"/ai/conversations/{conv_id}", headers=h1)
    ok("删除主会话 200", r.status_code == 200)
    with eng.connect() as conn:
        n_msg = conn.execute(text(
            "SELECT COUNT(*) FROM message WHERE conversation_id = :cid"), {"cid": conv_id}).scalar()
        n_src = conn.execute(text(
            "SELECT COUNT(*) FROM message_source s JOIN message m ON m.id = s.message_id "
            "WHERE m.conversation_id = :cid"), {"cid": conv_id}).scalar()
    ok("级联删除后 message 0 行", n_msg == 0, f"msg={n_msg}")
    ok("级联删除后 message_source 0 行", n_src == 0, f"src={n_src}")

    print("\n== T11 并发冒烟（2 线程不同会话）==")
    def chat_once(token: str, q: str) -> tuple[str, bool]:
        with new_client() as cc:
            hh = {"Authorization": f"Bearer {token}"}
            st, ev = sse_chat(cc, token, {"message": q})
            return (f"status={st}", bool(ev and ev[-1].get("event") == "done"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(chat_once, tok1, "生产经营单位应当如何开展事故隐患排查？")
        f2 = pool.submit(chat_once, tok2, "应急预案的演练频次有什么要求？")
        r1, r2 = f1.result(), f2.result()
    ok("并发线程1 完成", r1[0] == "status=200" and r1[1], f"{r1}")
    ok("并发线程2 完成", r2[0] == "status=200" and r2[1], f"{r2}")

    print(f"\n===== 结果：{len(FAILURES)} 个失败 =====")
    if FAILURES:
        print("失败项：", "；".join(FAILURES))
        sys.exit(1)
    print("全部通过 ✅")


if __name__ == "__main__":
    main()
