# -*- coding: utf-8 -*-
"""H04-H06 派单/整改/验收 + 难度过滤 + 干扰项溯源 + 负样本回流 验证。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_hazard_flow.py
前置：后端 8000 端口（含本轮新代码）。
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
ROOT = os.environ.get("ROOT_URL", BASE.removesuffix("/api/v1"))
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
            if httpx.get(ROOT + "/", timeout=10).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(2)

    c = httpx.Client(base_url=BASE, timeout=120)
    r = c.post("/auth/login", data={"username": "admin", "password": "Admin@123456"})
    assert r.json()["code"] == 200, "admin 登录失败"
    admin_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    # 员工（上报人）+ 整改负责人（员工2）
    emp1 = f"t_hz1_{ts}"
    emp2 = f"t_hz2_{ts}"
    for un, nm in ((emp1, "上报人"), (emp2, "整改负责人")):
        c.post("/auth/register", json={"username": un, "password": "Test@123456", "name": nm})
    r = c.post("/auth/login", data={"username": emp1, "password": "Test@123456"})
    emp1_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}
    r = c.post("/auth/login", data={"username": emp2, "password": "Test@123456"})
    emp2_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}
    # 拿整改负责人 id
    r = c.get("/users", params={"keyword": emp2, "page_size": 5}, headers=admin_h)
    handler_id = r.json()["data"]["items"][0]["id"]

    # ===== H04-H06 全流程 =====
    section("H04 派单")
    r = c.post("/hazards", json={"description": "派单流程测试-配电箱门敞开", "level": "MAJOR",
                                 "type": "用电安全"}, headers=emp1_h)
    hid = r.json()["data"]["id"]
    ok("上报成功 WAIT_PROCESS", r.json()["data"]["status"] == "WAIT_PROCESS")

    # 员工无权派单（403）
    r = c.post(f"/hazards/{hid}/dispatch", json={"handler_id": handler_id}, headers=emp1_h)
    ok("员工派单 403", r.status_code == 403, f"got {r.status_code}")
    # 管理员派单
    deadline = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    r = c.post(f"/hazards/{hid}/dispatch",
               json={"handler_id": handler_id, "deadline": deadline}, headers=admin_h)
    d = r.json()["data"]
    ok("管理员派单 → PROCESSING", r.status_code == 200 and d["status"] == "PROCESSING",
       f"status={d.get('status')}")
    # 重复派单 400
    r = c.post(f"/hazards/{hid}/dispatch", json={"handler_id": handler_id}, headers=admin_h)
    ok("重复派单 400", r.status_code == 400, f"got {r.status_code}")
    # 派单给不存在用户 400
    r = c.post("/hazards", json={"description": "派单测试2", "level": "MINOR"}, headers=emp1_h)
    hid2 = r.json()["data"]["id"]
    r = c.post(f"/hazards/{hid2}/dispatch", json={"handler_id": 999999}, headers=admin_h)
    ok("派单给不存在用户 400", r.status_code == 400, f"got {r.status_code}")

    section("H05 整改")
    # 无关员工整改 403
    r = c.post(f"/hazards/{hid}/rectify", json={"rectification_measure": "别人乱改"},
               headers=emp1_h)
    ok("非负责人整改 403", r.status_code == 403, f"got {r.status_code}")
    # 负责人整改
    r = c.post(f"/hazards/{hid}/rectify",
               json={"rectification_measure": "已更换配电箱并加锁", "rectification_images": []},
               headers=emp2_h)
    d = r.json()["data"]
    ok("负责人整改 → WAIT_CHECK", r.status_code == 200 and d["status"] == "WAIT_CHECK",
       f"status={d.get('status')}")
    # 详情含整改措施与负责人
    r = c.get(f"/hazards/{hid}", headers=emp1_h)
    dd = r.json()["data"]
    ok("详情含 handler_name/整改措施",
       dd.get("handler_name") == "整改负责人" and dd.get("rectification_measure") == "已更换配电箱并加锁",
       f"handler={dd.get('handler_name')} measure={dd.get('rectification_measure')}")

    section("H06 验收")
    # 待处理状态不能验收（用 hid2 测试状态机）
    r = c.post(f"/hazards/{hid2}/check", json={"passed": True}, headers=admin_h)
    ok("非待验收状态验收 400", r.status_code == 400, f"got {r.status_code}")
    # 驳回必须填原因
    r = c.post(f"/hazards/{hid}/check", json={"passed": False}, headers=admin_h)
    ok("驳回无原因 400", r.status_code == 400, f"got {r.status_code}")
    # 驳回 → REJECTED
    r = c.post(f"/hazards/{hid}/check", json={"passed": False, "reject_reason": "整改不彻底"},
               headers=admin_h)
    d = r.json()["data"]
    ok("驳回 → REJECTED", r.status_code == 200 and d["status"] == "REJECTED",
       f"status={d.get('status')}")
    r = c.get(f"/hazards/{hid}", headers=emp1_h)
    ok("驳回原因落库", r.json()["data"]["reject_reason"] == "整改不彻底")
    # 验收通过路径（重新走一条）
    r = c.post("/hazards", json={"description": "验收通过测试-临边无防护", "level": "CRITICAL"},
               headers=emp1_h)
    hid3 = r.json()["data"]["id"]
    c.post(f"/hazards/{hid3}/dispatch", json={"handler_id": handler_id}, headers=admin_h)
    c.post(f"/hazards/{hid3}/rectify", json={"rectification_measure": "已加装防护栏"},
           headers=emp2_h)
    r = c.post(f"/hazards/{hid3}/check", json={"passed": True}, headers=admin_h)
    d = r.json()["data"]
    ok("验收通过 → FINISHED", r.status_code == 200 and d["status"] == "FINISHED",
       f"status={d.get('status')}")
    # 时间线含派单/整改/验收
    r = c.get(f"/hazards/{hid3}", headers=emp1_h)
    ops = [lg["operation"] for lg in r.json()["data"]["timeline"]]
    ok("时间线含 派单/整改/验收", "派单" in ops and "整改" in ops and "验收" in ops, f"ops={ops}")
    # 闭环按钮兼容：H03 一键闭环仍可用（对 WAIT_PROCESS 的）
    r = c.post(f"/hazards/{hid2}/close", headers=admin_h)
    ok("H03 一键闭环兼容保留", r.status_code == 200 and r.json()["data"]["status"] == "FINISHED")

    section("AI 出题难度过滤 + 干扰项溯源 + 负样本回流（真实 LLM）")
    r = c.post("/ai/generate", json={
        "knowledge_point": "高处作业", "types": ["SINGLE"], "difficulty": "HARD", "count": 5,
    }, headers=admin_h)
    body = r.json()
    if body["code"] == 200:
        batch_id = body["data"]["batch_id"]
        r2 = c.get(f"/ai/batches/{batch_id}", headers=admin_h)
        items = r2.json()["data"]["questions"]
        ok("AI 出题批次 5 题", len(items) == 5, f"n={len(items)}")
        # 干扰项溯源：SINGLE 题自动置位（有选项的题）
        singles = [q for q in items if q["type"] == "SINGLE"]
        ok("干扰项溯源自动置位（interference_verified=1）",
           all(q["interference_verified"] == 1 for q in singles),
           f"verified={[q['interference_verified'] for q in singles]}")
        # 难度过滤：HARD 请求的批次，题型题面难度标注
        ok("批次题 difficulty=HARD", all(q["difficulty"] == "HARD" for q in items),
           f"diffs={sorted({q['difficulty'] for q in items})}")
    else:
        ok("AI 出题（需 LLM 配置）", False, f"msg={body.get('message')}")

    section("负样本回流（驳回 → 反例文件）")
    # 找一张 AI PENDING 题并驳回
    r = c.get("/ai/batches", headers=admin_h)
    batches = r.json()["data"]
    target = None
    for b in batches:
        r2 = c.get(f"/ai/batches/{b['batch_id']}", headers=admin_h)
        for q in r2.json()["data"].get("questions", []):
            if q["status"] == "PENDING":
                target = q
                break
        if target:
            break
    if target:
        r = c.post(f"/ai/questions/{target['id']}/review",
                   json={"action": "REJECT", "review_note": "负样本测试-题干有歧义"},
                   headers=admin_h)
        ok("驳回 AI 题 200", r.status_code == 200 and r.json()["code"] == 200)
        import os
        import json
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "rejected_examples.json")
        if os.path.exists(p):
            data = json.load(open(p, encoding="utf-8"))
            ok("反例库已写入（含驳回意见）",
               any("负样本测试" in (x.get("review_note") or "") for x in data),
               f"n={len(data)}")
        else:
            ok("反例库文件已生成", False, f"{p} 不存在")
    else:
        ok("未找到 AI PENDING 题，负样本分支跳过", True)

    c.close()
    print(f"\n{'='*60}\n结果：PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("H04-H06 + AI 增强验证全部通过 ✅")


if __name__ == "__main__":
    main()
