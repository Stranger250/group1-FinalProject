"""E04 在线考试 + E05 自动阅卷 端到端测试（对齐设计评审 testMatrix A1-A13）。

前置：后端已在 8000 端口运行（uvicorn app.main:app --reload），MySQL shudao 库就绪。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_exam_e2e.py

覆盖：
  A1 超时自动交卷(reason=timeout)  A2 刷新恢复(_exam_sheet)   A3 切屏(第4次触发 cheat_limit)
  A4 时长 422（E03 已验，此处复查一例）  A5 交卷全对 100 PASS   A6 成绩单(result 全字段)
  A7 多选集合比对(漏选 0 分)      A8 归一化(小写/乱序/全角分号) A9 越权(他人记录 404 掩码，管理员放行)
  A10 并发双交(只评一次，分数一致) A11 幂等 upsert(重复 save 覆盖不增行)
  A12 空卷交卷(全 0 分 FAIL + 占位行)  A13 脱敏(进行中题目不含 answer/analysis)
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 脚本位于 backend/scripts/，把 backend 根加入 sys.path 以便 import app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000/api/v1")
FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> bool:
    if not cond:
        FAILURES.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""))
    return cond


def new_client() -> httpx.Client:
    return httpx.Client(base_url=BASE, trust_env=False, timeout=30)


def login(client: httpx.Client, username: str, password: str) -> str:
    r = client.post("/auth/login", data={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["data"]["access_token"]


def register_or_login(client: httpx.Client, username: str, password: str, name: str) -> str:
    r = client.post("/auth/register", json={"username": username, "password": password, "name": name})
    if r.status_code == 200:
        return login(client, username, password)
    return login(client, username, password)


def create_published_paper(client: httpx.Client, admin_tok: str, name: str, items: list[tuple[int, int]], pass_score: int, duration: int = 30) -> int:
    """手动组卷并发布：items=[(question_id, score)]，返回 paper id。"""
    h = {"Authorization": f"Bearer {admin_tok}"}
    body = {
        "name": name,
        "duration": duration,
        "pass_score": pass_score,
        "total_score": sum(s for _, s in items),
        "questions": [{"question_id": qid, "score": score} for qid, score in items],
    }
    r = client.post("/papers/manual", json=body, headers=h)
    assert r.status_code == 200, f"组卷失败 {name}: {r.status_code} {r.text}"
    pid = r.json()["data"]["id"]
    r2 = client.put(f"/papers/{pid}", json={"status": "PUBLISHED"}, headers=h)
    assert r2.status_code == 200, f"发布失败 {name}: {r2.status_code} {r2.text}"
    return pid


# ---------- 主流程 ----------

def main() -> None:
    c = new_client()
    admin_tok = login(c, "admin", "Admin@123456")
    a = {"Authorization": f"Bearer {admin_tok}"}

    # 预置题库题目 id（q2 MULTIPLE、q3 JUDGE 因 bug 复现脚本误删，已按等价内容重建为 24/23）
    Q1, Q4, Q5, Q6 = 1, 4, 5, 6
    Q2, Q3 = 24, 23

    # P1：覆盖 4 种题型的 100 分卷（60 及格）
    #   q1 SINGLE=A 20, q5 SINGLE=A 20, q6 SINGLE=B 20, q2 MULTIPLE=A,B 20, q3 JUDGE=A 10, q4 FILL='安全第一;预防为主' 10
    P1 = create_published_paper(
        c, admin_tok, "E04测试-全题型",
        [(Q1, 20), (Q5, 20), (Q6, 20), (Q2, 20), (Q3, 10), (Q4, 10)], pass_score=60
    )
    P2 = create_published_paper(c, admin_tok, "E04测试-切屏", [(Q1, 10), (Q5, 10)], pass_score=12)
    P3 = create_published_paper(c, admin_tok, "E04测试-超时", [(Q1, 10), (Q5, 10)], pass_score=12)
    P4 = create_published_paper(c, admin_tok, "E04测试-空卷", [(Q1, 10), (Q5, 10)], pass_score=12)

    emp01 = register_or_login(c, "emp_t1", "123456", "考生一")
    emp02 = register_or_login(c, "emp_t2", "123456", "考生二")
    emp03 = register_or_login(c, "emp_t3", "123456", "考生三")
    e1, e2, e3 = {"Authorization": f"Bearer {emp01}"}, {"Authorization": f"Bearer {emp02}"}, {"Authorization": f"Bearer {emp03}"}

    print("\n== T1 A2+A13 开始考试 & 脱敏 ==")
    r = c.post("/exams/start", json={"paper_id": P1}, headers=e1)
    assert r.status_code == 200, f"start 失败: {r.status_code} {r.text}"
    sheet = r.json()["data"]
    rid = sheet["record_id"]
    ok("start 返回 ONGOING", sheet["state"] == "ONGOING", f"state={sheet['state']}")
    ok("start 返回 6 题", len(sheet["questions"]) == 6, f"n={len(sheet['questions'])}")
    ok("A13 题目不含 answer", all("answer" not in q and "analysis" not in q for q in sheet["questions"]))
    ok("A13 不含正确作答字段", all("correct_answer" not in q for q in sheet["questions"]))
    ok("answers 初始为空", sheet["answers"] == [])
    ok("含倒计时", sheet["remaining_seconds"] > 0 and sheet["deadline"], f"remain={sheet['remaining_seconds']}")
    ok("总分/及格线正确", sheet["total_score"] == 100 and sheet["pass_score"] == 60)

    print("\n== T2 A11 幂等 upsert ==")
    r = c.post(f"/exams/{rid}/save", json={"answers": [{"question_id": Q1, "user_answer": "B"}]}, headers=e1)
    assert r.status_code == 200
    r = c.post(f"/exams/{rid}/save", json={"answers": [{"question_id": Q1, "user_answer": "A"}]}, headers=e1)
    r = c.get(f"/exams/{rid}", headers=e1)
    saved = {a["question_id"]: a["user_answer"] for a in r.json()["data"]["answers"]}
    ok("save 覆盖最后值", saved.get(Q1) == "A", f"q1={saved.get(Q1)!r}")
    ok("state 仍 ONGOING", r.json()["data"]["state"] == "ONGOING")

    print("\n== T3 A8 归一化保存（小写/乱序/全角分号）==")
    r = c.post(
        f"/exams/{rid}/save",
        json={"answers": [
            {"question_id": Q6, "user_answer": "b"},            # SINGLE 小写
            {"question_id": Q2, "user_answer": "b,a"},          # MULTIPLE 乱序小写
            {"question_id": Q4, "user_answer": "安全第一；预防为主"},  # FILL 全角分号
            {"question_id": Q3, "user_answer": "a"},            # JUDGE 小写
            {"question_id": Q5, "user_answer": "A"},
        ]},
        headers=e1,
    )
    ok("保存成功且未交卷", r.status_code == 200 and r.json()["data"]["state"] == "ONGOING")

    print("\n== T4 A3 切屏上报（不触发）==")
    last = None
    for i in (1, 2, 3):
        last = c.post(f"/exams/{rid}/switch", json={"cheat_count": i}, headers=e1).json()["data"]
    ok("3 次切屏不触发", last.get("triggered") is False and last["cheat_count"] == 3, f"cheat={last['cheat_count']}")

    print("\n== T5 A5+A7+A8 交卷自动阅卷 ==")
    r = c.post(f"/exams/{rid}/submit", json={"answers": [
        {"question_id": Q1, "user_answer": "A"},
        {"question_id": Q5, "user_answer": "A"},
        {"question_id": Q6, "user_answer": "b"},
        {"question_id": Q2, "user_answer": "b,a"},
        {"question_id": Q3, "user_answer": "a"},
        {"question_id": Q4, "user_answer": "安全第一；预防为主"},
    ]}, headers=e1)
    d = r.json()["data"]
    ok("全对 100 分 PASS", d["total_score"] == 100 and d["status"] == "PASS" and d["passed"], f"score={d['total_score']} status={d['status']}")
    ok("手动交卷 reason=manual", d["reason"] == "manual", f"reason={d['reason']}")
    ok("state=SUBMITTED", d["state"] == "SUBMITTED")
    q_map = {q["question_id"]: q for q in d["questions"]}
    ok("每题都判对", all(v["is_correct"] == 1 and v["score"] == v2 for v, v2 in
                        [(q_map[qid], sc) for qid, sc in [(Q1, 20), (Q5, 20), (Q6, 20), (Q2, 20), (Q3, 10), (Q4, 10)]]))
    ok("A8 多选乱序判对", q_map[Q2]["user_answer"] == "A,B" and q_map[Q2]["is_correct"] == 1, f"q2={q_map[Q2]['user_answer']!r}")
    ok("A8 填空全角分号判对", q_map[Q4]["is_correct"] == 1, f"q4={q_map[Q4]['user_answer']!r}")

    print("\n== T6 A6+A9 成绩单 & 越权 ==")
    r = c.get(f"/exams/{rid}/result", headers=e1)
    rs = r.json()["data"]
    ok("成绩单字段齐全", all(k in rs for k in (
        "record_id", "paper_id", "paper_name", "state", "status", "reason",
        "total_score", "pass_score", "passed", "submitted_at", "start_time",
        "duration", "cheat_count", "questions")))
    ok("成绩单含解析与正确答案", rs["questions"] and "analysis" in rs["questions"][0] and "correct_answer" in rs["questions"][0])
    ok("A9 他人访问 404（掩码，防记录枚举）", c.get(f"/exams/{rid}/result", headers=e2).status_code == 404)
    ok("A9 管理员放行", c.get(f"/exams/{rid}/result", headers=a).status_code == 200)
    ok("A9 交卷后 resume 幂等返回成绩单", c.get(f"/exams/{rid}", headers=e1).json()["data"]["state"] == "SUBMITTED")
    ok("A9 交卷后 submit 幂等返回成绩单", c.post(f"/exams/{rid}/submit", json={"answers": [{"question_id": Q1, "user_answer": "B"}]}, headers=e1).json()["data"]["total_score"] == 100)

    print("\n== T7 A7 多选漏选 0 分 ==")
    r = c.post("/exams/start", json={"paper_id": P1}, headers=e1)
    rid2 = r.json()["data"]["record_id"]
    r = c.post(f"/exams/{rid2}/submit", json={"answers": [
        {"question_id": Q1, "user_answer": "A"},
        {"question_id": Q5, "user_answer": "A"},
        {"question_id": Q6, "user_answer": "B"},
        {"question_id": Q2, "user_answer": "A"},   # 漏选 B → 0 分
        {"question_id": Q3, "user_answer": "A"},
        {"question_id": Q4, "user_answer": "安全第一;预防为主"},
    ]}, headers=e1)
    d = r.json()["data"]
    q2m = {q["question_id"]: q for q in d["questions"]}[Q2]
    ok("漏选 MULTIPLE 0 分", q2m["is_correct"] == 0 and q2m["score"] == 0, f"q2 score={q2m['score']}")
    ok("总分 80 仍 PASS(≥60)", d["score"] == 80 and d["status"] == "PASS", f"score={d['score']} status={d['status']}")

    print("\n== T8 A3 切屏第 4 次触发自动交卷 ==")
    r = c.post("/exams/start", json={"paper_id": P2}, headers=e2)
    rid3 = r.json()["data"]["record_id"]
    triggered = None
    for i in (1, 2, 3, 4):
        triggered = c.post(f"/exams/{rid3}/switch", json={"cheat_count": i}, headers=e2).json()["data"]
    ok("第 4 次切屏自动交卷", triggered.get("state") == "SUBMITTED", f"state={triggered.get('state')}")
    ok("reason=cheat_limit", triggered.get("reason") == "cheat_limit", f"reason={triggered.get('reason')}")

    print("\n== T9 A1 超时自动交卷 ==")
    r = c.post("/exams/start", json={"paper_id": P3}, headers=e2)
    rid4 = r.json()["data"]["record_id"]
    # 用 SQL 把 start_time 拨回 31 分钟前（duration=30 → 已超时）
    from sqlalchemy import create_engine, text
    from app.core.config import get_settings
    eng = create_engine(get_settings().database_url)
    with eng.begin() as conn:
        conn.execute(text("UPDATE exam_record SET start_time = DATE_SUB(NOW(), INTERVAL 31 MINUTE) WHERE id = :rid"), {"rid": rid4})
    r = c.get(f"/exams/{rid4}", headers=e2)
    d = r.json()["data"]
    ok("超时 resume 自动交卷", d["state"] == "SUBMITTED", f"state={d['state']}")
    ok("reason=timeout", d["reason"] == "timeout", f"reason={d['reason']}")
    ok("超时未作答 0 分 FAIL", d["score"] == 0 and d["passed"] is False, f"score={d['score']}")

    print("\n== T10 A12 空卷交卷 ==")
    r = c.post("/exams/start", json={"paper_id": P4}, headers=e3)
    rid5 = r.json()["data"]["record_id"]
    r = c.post(f"/exams/{rid5}/submit", json={"answers": []}, headers=e3)
    d = r.json()["data"]
    ok("空卷 0 分 FAIL", d["score"] == 0 and d["status"] == "FAIL", f"score={d['score']}")
    ok("每题占位行 user_answer=''", all(q["user_answer"] == "" and q["is_correct"] == 0 for q in d["questions"]))

    print("\n== T11 A10 并发双交（只评一次，分数一致）==")
    r = c.post("/exams/start", json={"paper_id": P1}, headers=e1)
    rid6 = r.json()["data"]["record_id"]

    def submit_thread(token: str, answers: list[dict]) -> dict:
        with new_client() as cc:
            resp = cc.post(f"/exams/{rid6}/submit", json={"answers": answers},
                           headers={"Authorization": f"Bearer {token}"})
            try:
                body = resp.json()["data"]
            except Exception:
                body = {"status": resp.status_code, "text": resp.text[:200]}
            return body

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(submit_thread, emp01, [{"question_id": Q1, "user_answer": "A"}])
        f2 = pool.submit(submit_thread, emp01, [{"question_id": Q1, "user_answer": "A"}, {"question_id": Q5, "user_answer": "A"}])
        r1, r2 = f1.result(), f2.result()
    ok("双请求均返回成绩单", r1.get("state") == "SUBMITTED" and r2.get("state") == "SUBMITTED",
       f"r1={r1.get('state')} r2={r2.get('state')}")
    ok("双请求分数一致", r1.get("total_score") == r2.get("total_score"), f"{r1.get('total_score')} vs {r2.get('total_score')}")
    # 明细表无重复：每 (record,question) 仅一行
    with eng.connect() as conn:
        dup = conn.execute(text(
            "SELECT question_id, COUNT(*) FROM exam_answer WHERE record_id = :rid GROUP BY question_id HAVING COUNT(*) > 1"
        ), {"rid": rid6}).fetchall()
    ok("answer 表无重复行", not dup, f"dup={dup}")

    print("\n== A4 时长 422（复查）==")
    r = c.post("/papers/manual", json={
        "name": "E04测试-非法时长", "duration": 45, "pass_score": 60, "total_score": 100,
        "questions": [{"question_id": Q1, "score": 100}],
    }, headers=a)
    ok("duration=45 被 422 拒绝", r.status_code == 422, f"status={r.status_code}")

    print(f"\n===== 结果：{len(FAILURES)} 个失败 / 38 项 =====")
    if FAILURES:
        print("失败项：", "；".join(FAILURES))
        sys.exit(1)
    print("全部通过 ✅")


if __name__ == "__main__":
    main()
