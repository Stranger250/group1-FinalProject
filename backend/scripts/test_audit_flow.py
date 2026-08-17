# -*- coding: utf-8 -*-
"""O13 验证：安全员隐患处理（模拟）+ 数据隔离（普通用户仅见本人上报）。

用法: python scripts/test_audit_flow.py   （BASE_URL 可覆盖，默认 8002）
覆盖：
  1) 员工上报隐患 → audit_status=pending
  2) 普通用户列表/详情仅本人上报（越权 404）
  3) 安全员可见全部（列表含他人隐患）
  4) 安全员处理（已处理/驳回 + 意见）→ 详情 audit_* 字段
  5) 上报人可见处理状态与结果
"""
import os
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

import requests

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8002/api/v1")
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


def login(username: str, password: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", data={"username": username, "password": password}, timeout=20)
    assert r.status_code == 200 and r.json()["code"] == 200, f"login {username} failed: {r.text[:200]}"
    return {"Authorization": "Bearer " + r.json()["data"]["access_token"]}


def register(username: str, name: str) -> None:
    r = requests.post(f"{BASE}/auth/register", json={"username": username, "password": "Test@123456", "name": name}, timeout=20)
    assert r.status_code == 200, f"register {username}: {r.text[:200]}"


def main() -> None:
    ts = datetime.now().strftime("%H%M%S")
    emp1 = f"t_au1_{ts}"
    emp2 = f"t_au2_{ts}"
    register(emp1, "上报人甲")
    register(emp2, "上报人乙")
    h1 = login(emp1, "Test@123456")
    h2 = login(emp2, "Test@123456")
    ha = login("admin", "Admin@123456")

    # 1) 员工上报两条隐患
    c1 = requests.post(f"{BASE}/hazards", headers=h1, json={
        "description": "O13测试：甲上报的配电箱隐患", "level": "MAJOR", "type": "用电安全"}, timeout=20)
    ok("员工1上报 200", c1.status_code == 200, c1.text[:120])
    hid1 = c1.json()["data"]["id"]
    d1 = c1.json()["data"]
    ok("上报后 audit_status=pending", d1.get("audit_status") == "pending", str(d1.get("audit_status")))

    c2 = requests.post(f"{BASE}/hazards", headers=h2, json={
        "description": "O13测试：乙上报的临边隐患", "level": "GENERAL", "type": "临边防护"}, timeout=20)
    hid2 = c2.json()["data"]["id"]

    # 2) 数据隔离：员工1 列表仅见自己的；详情访问员工2 的 → 404
    lst1 = requests.get(f"{BASE}/hazards", headers=h1, params={"page_size": 50}, timeout=20).json()["data"]
    mine_ids = {i["id"] for i in lst1["items"]}
    ok("员工1 列表仅含本人上报", hid1 in mine_ids and hid2 not in mine_ids, f"hid1={hid1} hid2={hid2} total={lst1['total']}")
    r_other = requests.get(f"{BASE}/hazards/{hid2}", headers=h1, timeout=20)
    ok("员工1 访问他人详情 404", r_other.status_code == 404, f"status={r_other.status_code}")

    # 3) 安全员可见全部
    lst_admin = requests.get(f"{BASE}/hazards", headers=ha, params={"page_size": 50}, timeout=20).json()["data"]
    admin_ids = {i["id"] for i in lst_admin["items"]}
    ok("安全员(admin)可见全部", hid1 in admin_ids and hid2 in admin_ids, "")
    d_admin = requests.get(f"{BASE}/hazards/{hid1}", headers=ha, timeout=20).json()["data"]
    ok("详情含 audit_* 字段", all(k in d_admin for k in ("audit_status", "audit_by", "audit_at", "audit_comment")), "")

    # 4) 处理：已处理 + 意见
    rp = requests.post(f"{BASE}/hazards/{hid1}/audit", headers=ha, json={"passed": True, "comment": "现场核实，已安排整改"}, timeout=20)
    ok("标记已处理 200", rp.status_code == 200, rp.text[:120])
    d1b = requests.get(f"{BASE}/hazards/{hid1}", headers=h1, timeout=20).json()["data"]
    ok("处理状态=approved", d1b.get("audit_status") == "approved", str(d1b.get("audit_status")))
    ok("处理意见已落库", d1b.get("audit_comment") == "现场核实，已安排整改", str(d1b.get("audit_comment")))
    ok("处理时间已记录", bool(d1b.get("audit_at")), str(d1b.get("audit_at")))

    # 5) 驳回必须填意见
    rb = requests.post(f"{BASE}/hazards/{hid2}/audit", headers=ha, json={"passed": False, "comment": ""}, timeout=20)
    ok("驳回无意见 400", rb.status_code == 400, f"status={rb.status_code}")
    rb2 = requests.post(f"{BASE}/hazards/{hid2}/audit", headers=ha, json={"passed": False, "comment": "照片不清晰，请补充"}, timeout=20)
    ok("驳回（含意见）200", rb2.status_code == 200, rb2.text[:120])
    d2b = requests.get(f"{BASE}/hazards/{hid2}", headers=h2, timeout=20).json()["data"]
    ok("驳回状态=rejected 且意见可见", d2b.get("audit_status") == "rejected" and d2b.get("audit_comment") == "照片不清晰，请补充", "")

    # 6) 普通用户无处理权限
    rp2 = requests.post(f"{BASE}/hazards/{hid2}/audit", headers=h1, json={"passed": True}, timeout=20)
    ok("普通用户处理 403", rp2.status_code == 403, f"status={rp2.status_code}")

    print(f"\nO13 验证结果: PASS={PASS} FAIL={FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
