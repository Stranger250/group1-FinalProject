# -*- coding: utf-8 -*-
"""新功能验证：审计日志 / 敏感词输出复检 / 出题批次内去重 / 回归。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_new_features.py
前置：后端 8001 端口（含本轮新增代码）。
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
    # 预热
    for i in range(6):
        try:
            if httpx.get("http://127.0.0.1:8001/", timeout=10).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(2)

    c = httpx.Client(base_url=BASE, timeout=120)
    r = c.post("/auth/login", data={"username": "admin", "password": "Admin@123456"})
    assert r.json()["code"] == 200, "admin 登录失败"
    admin_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    uname = f"t_new_{ts}"
    r = c.post("/auth/register", json={"username": uname, "password": "Test@123456", "name": "新功能"})
    assert r.status_code == 200, "注册失败"
    r = c.post("/auth/login", data={"username": uname, "password": "Test@123456"})
    emp_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    # ===== 1. 审计日志 =====
    section("审计日志（登录/闭环/审核/试卷状态）")
    r = c.post("/auth/login", data={"username": "no_such_user_audit", "password": "wrong"})
    ok("登录失败仍返回 401", r.status_code == 401)
    r = c.post("/hazards", json={"description": "审计测试隐患", "level": "GENERAL"}, headers=emp_h)
    hid = r.json()["data"]["id"]
    r = c.post(f"/hazards/{hid}/close", headers=admin_h)
    ok("闭环成功", r.status_code == 200)
    r = c.post("/papers/manual", json={
        "name": f"审计卷-{ts}", "duration": 30, "total_score": 30, "pass_score": 18,
        "questions": []}, headers=admin_h) if False else None
    # 试卷状态变更审计
    r = c.get("/questions", params={"status": "APPROVED", "page_size": 1}, headers=admin_h)
    qid = r.json()["data"]["items"][0]["id"]
    r = c.post("/papers/manual", json={
        "name": f"审计卷-{ts}", "duration": 30, "total_score": 30, "pass_score": 18,
        "questions": [{"question_id": qid, "score": 30}]}, headers=admin_h)
    pid = r.json()["data"]["id"]
    r = c.put(f"/papers/{pid}", json={"status": "PUBLISHED"}, headers=admin_h)
    ok("试卷发布成功", r.status_code == 200)
    time.sleep(1)

    import os
    import pymysql
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy.engine import make_url
    from app.core.config import get_settings
    _u = make_url(get_settings().database_url)
    dbc = pymysql.connect(host=_u.host, port=_u.port or 3306, user=_u.username,
                          password=_u.password or "", database=_u.database, charset="utf8mb4")
    cur = dbc.cursor()
    cur.execute("SELECT action, username, target_type, target_id FROM audit_log ORDER BY id DESC LIMIT 8")
    rows = cur.fetchall()
    actions = {r[0] for r in rows}
    ok("审计：login 成功留痕", "login" in actions, f"actions={sorted(actions)}")
    ok("审计：登录失败留痕", "login_failed" in actions)
    ok("审计：隐患闭环留痕", "hazard_close" in actions)
    ok("审计：试卷状态变更留痕", "paper_status" in actions)
    ok("审计：用户名冗余可追溯", all(r[1] for r in rows if r[0] == "login"))
    dbc.close()

    # ===== 2. 敏感词输出复检（LLM 流）=====
    section("敏感词输出复检（SSE 流）")
    # 入口预检仍拦截（400）
    r = c.post("/ai/chat", json={"message": "我想了解造谣的相关处罚"}, headers=emp_h)
    ok("入口敏感词预检 400", r.status_code == 400, f"got {r.status_code}")
    # 输出复检：正常问题走流（无敏感词时不受影响）
    r = c.post("/ai/chat", json={"message": "高处作业安全要求有哪些？"}, headers=emp_h)
    ok("正常问答 SSE 200 且含 meta/done", r.status_code == 200 and "meta" in r.text and "done" in r.text,
       f"len={len(r.text)}")

    # ===== 3. 出题批次内去重 =====
    section("AI 出题批次内去重（真实 LLM）")
    r = c.post("/ai/generate", json={
        "knowledge_point": "高处作业", "types": ["SINGLE"], "difficulty": "EASY", "count": 5,
    }, headers=admin_h)
    body = r.json()
    if body["code"] == 200:
        batch_id = body["data"]["batch_id"]
        r2 = c.get(f"/ai/batches/{batch_id}", headers=admin_h)
        items = r2.json()["data"]["questions"]
        contents = [q["content"] for q in items]
        import re
        norm = [re.sub(r"\s+", "", x) for x in contents]
        ok("批次内无重复题干", len(set(norm)) == len(norm), f"n={len(norm)} dup={len(norm)-len(set(norm))}")
    else:
        ok("AI 出题（需 LLM 配置）", False, f"msg={body.get('message')}")

    # ===== 4. 回归：解答题全链路 + 基础 =====
    section("回归冒烟")
    r = c.post("/questions", json={
        "type": "SUBJECTIVE", "content": "回归-简述动火作业前要求", "options": None,
        "answer": "办理许可证；清除可燃物；配备灭火器材", "analysis": "解析",
        "knowledge_point": "动火", "difficulty": "MEDIUM"}, headers=admin_h)
    ok("解答题录入回归", r.status_code == 200 and r.json()["code"] == 200)
    r = c.get("/ai/quick-questions", headers=emp_h)
    ok("快捷提问回归", r.status_code == 200)
    r = c.get("/hazards", headers=emp_h)
    ok("隐患列表回归", r.status_code == 200)

    c.close()

    print(f"\n{'='*60}\n结果：PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("新功能验证全部通过 ✅")


if __name__ == "__main__":
    main()
