# -*- coding: utf-8 -*-
"""解答题（SUBJECTIVE）全链路验证：手动录入 → AI 出题 → 组卷 → 考试作答 → 要点判分。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_subjective.py
前置：后端在 8001 端口（本次验证专用实例）。
"""
from __future__ import annotations

import sys
import time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx

BASE = "http://127.0.0.1:8001/api/v1"
PASS = 0
FAIL = 0
FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f" | {detail}" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name}" + (f" | {detail}" if detail else ""))
    return cond


def section(title: str) -> None:
    print(f"\n===== {title} =====")


def main() -> None:
    ts = datetime.now().strftime("%H%M%S")

    c = httpx.Client(base_url=BASE, timeout=120)
    # 预热
    for i in range(6):
        try:
            if httpx.get("http://127.0.0.1:8001/", timeout=10).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(2)

    r = c.post("/auth/login", data={"username": "admin", "password": "Admin@123456"})
    assert r.json()["code"] == 200, "admin 登录失败"
    admin_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    uname = f"t_subj_{ts}"
    r = c.post("/auth/register", json={"username": uname, "password": "Test@123456", "name": "解答题考生"})
    assert r.status_code == 200, "注册失败"
    r = c.post("/auth/login", data={"username": uname, "password": "Test@123456"})
    emp_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    # ===== 1. 手动录入解答题 =====
    section("手动录入解答题")
    payload = {
        "type": "SUBJECTIVE",
        "content": "简述高处作业人员的基本安全要求。",
        "options": None,
        "answer": "必须佩戴安全帽；高处作业必须系安全带；作业前进行安全交底",
        "analysis": "依据高处作业管理规定，作业人员应正确佩戴个人防护用品，系挂安全带，并接受安全交底。",
        "knowledge_point": "高处作业",
        "difficulty": "MEDIUM",
    }
    r = c.post("/questions", json=payload, headers=admin_h)
    body = r.json()
    ok("录入解答题 200", r.status_code == 200 and body["code"] == 200)
    qid = body.get("data", {}).get("id")
    ok("解答题直接 APPROVED", body.get("data", {}).get("status") == "APPROVED")
    ok("解答题 options=null", body.get("data", {}).get("options") is None)
    ok("长答案完整保存", body.get("data", {}).get("answer") == payload["answer"])

    # 边界：空要点
    r = c.post("/questions", json={**payload, "answer": "要点1；；要点2"}, headers=admin_h)
    ok("空要点答案 → 400", r.status_code == 400, f"got {r.status_code}")

    # ===== 2. 组卷 =====
    section("解答题组卷")
    r = c.post("/papers/manual", json={
        "name": f"解答题卷-{ts}", "duration": 30, "total_score": 30, "pass_score": 18,
        "questions": [{"question_id": qid, "score": 30}]}, headers=admin_h)
    body = r.json()
    ok("手动组卷含解答题 200", r.status_code == 200 and body["code"] == 200, f"msg={body.get('message')}")
    pid = body.get("data", {}).get("id")
    r = c.put(f"/papers/{pid}", json={"status": "PUBLISHED"}, headers=admin_h)
    ok("发布试卷 200", r.status_code == 200 and r.json()["code"] == 200)

    # ===== 3. 考试作答 =====
    section("解答题考试作答")
    r = c.post("/exams/start", json={"paper_id": pid}, headers=emp_h)
    body = r.json()
    ok("开始考试 200", body["code"] == 200, f"state={body.get('data', {}).get('state')}")
    rec_id = body["data"]["record_id"]
    qs = body["data"]["questions"]
    ok("试卷含解答题（脱敏无答案）", len(qs) == 1 and qs[0]["type"] == "SUBJECTIVE"
       and "answer" not in qs[0] and "analysis" not in qs[0])

    # 保存完整答案（逐字包含全部 3 个要点；判分为严格子串包含）
    full_ans = "必须佩戴安全帽，高处作业必须系安全带，作业前进行安全交底"
    r = c.post(f"/exams/{rec_id}/save", json={"answers": [{"question_id": qid, "user_answer": full_ans}]}, headers=emp_h)
    ok("保存解答题答案 200", r.status_code == 200 and r.json()["code"] == 200)
    # 保存超长答案（>255 字符，验证 TEXT 列）
    long_ans = "必须佩戴安全帽。" * 60
    r = c.post(f"/exams/{rec_id}/save", json={"answers": [{"question_id": qid, "user_answer": long_ans}]}, headers=emp_h)
    ok("超长解答(>255字)保存 200", r.status_code == 200 and r.json()["code"] == 200, f"got {r.status_code}")
    # 恢复完整答案
    r = c.post(f"/exams/{rec_id}/save", json={"answers": [{"question_id": qid, "user_answer": full_ans}]}, headers=emp_h)

    # ===== 4. 交卷 + 要点判分 =====
    section("交卷 + 要点判分（满分 30 分）")
    r = c.post(f"/exams/{rec_id}/submit", json={"answers": [{"question_id": qid, "user_answer": full_ans}]}, headers=emp_h)
    d = r.json()["data"]
    q0 = d["questions"][0]
    ok("全部要点命中 → 满分 30", q0["is_correct"] == 1 and q0["score"] == 30,
       f"score={q0['score']} is_correct={q0['is_correct']}")
    ok("总分 30 PASS", d["score"] == 30 and d["passed"] is True, f"score={d['score']} passed={d['passed']}")
    ok("correct_answer 存参考答案快照", q0["correct_answer"] == payload["answer"].replace("；", ";"))

    # 部分命中 → 部分得分（新考试）
    section("部分命中判分")
    r = c.post("/exams/start", json={"paper_id": pid}, headers=emp_h)
    rec2 = r.json()["data"]["record_id"]
    partial_ans = "必须佩戴安全帽"  # 命中 1/3 要点 → round(30/3)=10
    r = c.post(f"/exams/{rec2}/submit", json={"answers": [{"question_id": qid, "user_answer": partial_ans}]}, headers=emp_h)
    d2 = r.json()["data"]
    q2 = d2["questions"][0]
    ok("命中 1/3 要点 → 10 分", q2["score"] == 10 and q2["is_correct"] == 0,
       f"score={q2['score']} is_correct={q2['is_correct']}")

    # 未作答 → 0 分
    section("未作答判分")
    r = c.post("/exams/start", json={"paper_id": pid}, headers=emp_h)
    rec3 = r.json()["data"]["record_id"]
    r = c.post(f"/exams/{rec3}/submit", json={"answers": []}, headers=emp_h)
    d3 = r.json()["data"]
    ok("未作答 → 0 分", d3["score"] == 0 and d3["passed"] is False, f"score={d3['score']}")

    # ===== 5. AI 出题（真实 LLM）=====
    section("AI 出题解答题（真实 LLM）")
    r = c.post("/ai/generate", json={
        "knowledge_point": "高处作业",
        "types": ["SUBJECTIVE"],
        "difficulty": "MEDIUM",
        "count": 5,
    }, headers=admin_h)
    body = r.json()
    if body["code"] == 200:
        batch_id = body["data"]["batch_id"]
        ok("AI 生成解答题批次 200", True, f"batch={batch_id}")
        r2 = c.get(f"/ai/batches/{batch_id}", headers=admin_h)
        items = r2.json()["data"]["questions"]
        ok("批次含 5 题且全为 SUBJECTIVE",
           len(items) == 5 and all(q["type"] == "SUBJECTIVE" for q in items), f"n={len(items)}")
        subj = items[0]
        ok("解答题 options=null", subj["options"] is None)
        ok("解答题答案含分号要点", ";" in subj["answer"] or "；" in subj["answer"],
           f"answer={str(subj['answer'])[:60]}")
        ok("解答题带法规溯源", bool(subj.get("source_law_title")) and bool(subj.get("source_article_no")))
    else:
        ok("AI 生成解答题（需 LLM 配置）", False, f"code={body.get('code')} msg={body.get('message')}")

    admin = httpx.Client(base_url=BASE, timeout=60)
    admin.post("/auth/login", data={"username": "admin", "password": "Admin@123456"})
    admin.close()
    c.close()

    print(f"\n{'='*60}\n结果：PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("解答题全链路测试全部通过 ✅")


if __name__ == "__main__":
    main()
