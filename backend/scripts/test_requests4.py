# -*- coding: utf-8 -*-
"""4 项需求验证：忘记密码重置 / 重置密码=123456 / 安全员处理隐患 / 智能问答流式输出。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_requests4.py
前置：后端 8000 端口。
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000/api/v1")
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
    for i in range(6):
        try:
            if httpx.get("http://127.0.0.1:8000/", timeout=10).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(2)

    c = httpx.Client(base_url=BASE, timeout=120)
    r = c.post("/auth/login", data={"username": "admin", "password": "Admin@123456"})
    assert r.json()["code"] == 200, "admin 登录失败"
    admin_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    # ===== 1. 忘记密码：请求重置 =====
    section("忘记密码请求重置")
    uname = f"t_fgt_{ts}"
    c.post("/auth/register", json={"username": uname, "password": "OldPass@123", "name": "忘记密码测试"})
    r = c.post("/auth/forgot-password", json={"username": uname})
    d = r.json()
    ok("忘记密码重置 200", r.status_code == 200 and d["code"] == 200, f"msg={d.get('message')}")
    ok("新密码为默认 123456", d["data"]["new_password"] == "123456")
    # 用新密码可登录
    r = c.post("/auth/login", data={"username": uname, "password": "123456"})
    ok("重置后可用 123456 登录", r.status_code == 200 and r.json()["code"] == 200)
    # 不存在用户 → 统一文案 404（防枚举）
    r = c.post("/auth/forgot-password", json={"username": "no_such_user_zzz"})
    ok("不存在用户 → 404 统一文案", r.status_code == 404 and "不存在" in r.json().get("message", ""),
       f"msg={r.json().get('message')}")
    # 审计留痕
    r = c.get("/logs", params={"action": "password_reset_request", "page_size": 5}, headers=admin_h)
    ok("审计记录 password_reset_request", r.status_code == 200 and r.json()["data"]["total"] >= 1)

    # ===== 2. 管理员重置密码 = 123456 =====
    section("管理员重置密码（固定 123456）")
    r = c.get("/users", params={"keyword": uname, "page_size": 5}, headers=admin_h)
    uid = r.json()["data"]["items"][0]["id"]
    r = c.post(f"/users/{uid}/reset-password", headers=admin_h)
    d = r.json()["data"]
    ok("管理员重置返回 123456", d["new_password"] == "123456", f"pw={d.get('new_password')}")
    r = c.post("/auth/login", data={"username": uname, "password": "123456"})
    ok("重置后登录成功", r.status_code == 200 and r.json()["code"] == 200)

    # ===== 3. 安全员处理隐患（H04-H06 角色验证）=====
    section("安全员处理隐患")
    # 建安全员账号（admin 改角色）
    safename = f"t_safe_{ts}"
    c.post("/auth/register", json={"username": safename, "password": "Test@123456", "name": "安全员"})
    r = c.get("/users", params={"keyword": safename, "page_size": 5}, headers=admin_h)
    safe_id = r.json()["data"]["items"][0]["id"]
    c.put(f"/users/{safe_id}", json={"role_id": 2}, headers=admin_h)
    r = c.post("/auth/login", data={"username": safename, "password": "Test@123456"})
    safe_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}
    # 员工上报
    empname = f"t_emp_{ts}"
    c.post("/auth/register", json={"username": empname, "password": "Test@123456", "name": "员工"})
    r = c.post("/auth/login", data={"username": empname, "password": "Test@123456"})
    emp_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}
    r = c.post("/hazards", json={"description": "安全员处理测试-电缆裸露", "level": "MAJOR"}, headers=emp_h)
    hid = r.json()["data"]["id"]
    # 安全员派单（给员工2）
    r = c.get("/users", params={"role_id": 1, "page_size": 3}, headers=admin_h)
    handler_id = r.json()["data"]["items"][0]["id"]
    r = c.post(f"/hazards/{hid}/dispatch", json={"handler_id": handler_id}, headers=safe_h)
    ok("安全员派单 200", r.status_code == 200 and r.json()["data"]["status"] == "PROCESSING",
       f"status={r.json().get('data', {}).get('status')}")
    # 安全员整改（管理角色可整改）
    r = c.post(f"/hazards/{hid}/rectify", json={"rectification_measure": "已穿管保护"}, headers=safe_h)
    ok("安全员整改 200", r.status_code == 200 and r.json()["data"]["status"] == "WAIT_CHECK")
    # 安全员验收通过
    r = c.post(f"/hazards/{hid}/check", json={"passed": True}, headers=safe_h)
    ok("安全员验收通过 → FINISHED", r.status_code == 200 and r.json()["data"]["status"] == "FINISHED",
       f"status={r.json().get('data', {}).get('status')}")
    # 员工无法派单（403）
    r = c.post("/hazards", json={"description": "越权测试", "level": "MINOR"}, headers=emp_h)
    hid2 = r.json()["data"]["id"]
    r = c.post(f"/hazards/{hid2}/dispatch", json={"handler_id": handler_id}, headers=emp_h)
    ok("员工派单 403", r.status_code == 403)

    # ===== 4. 智能问答流式输出 =====
    section("智能问答流式输出（SSE）")
    r = c.post("/auth/login", data={"username": empname, "password": "Test@123456"})
    emp2_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}
    with c.stream("POST", "/ai/chat", json={"message": "高处作业需要佩戴什么？"}, headers=emp2_h) as resp:
        assert resp.status_code == 200, f"chat status={resp.status_code}"
        chunks = []
        for line in resp.iter_lines():
            if line.startswith("event:"):
                chunks.append(line[6:].strip())
        ok("SSE 事件序 meta→delta→done", chunks and chunks[0] == "meta" and chunks[-1] == "done",
           f"events={chunks[:8]}…")
        ok("存在多个 delta 增量块（流式）", chunks.count("delta") >= 2,
           f"delta 块数={chunks.count('delta')}")

    c.close()
    print(f"\n{'='*60}\n结果：PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("4 项需求验证全部通过 ✅")


if __name__ == "__main__":
    main()
