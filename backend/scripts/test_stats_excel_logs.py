# -*- coding: utf-8 -*-
"""Excel 导入导出 / 考试统计 / 错题本 / 审计日志查询 验证。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_stats_excel_logs.py
前置：后端 8000 端口。
"""
from __future__ import annotations

import io
import sys
import time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
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

    uname = f"t_sel_{ts}"
    c.post("/auth/register", json={"username": uname, "password": "Test@123456", "name": "统计考生"})
    r = c.post("/auth/login", data={"username": uname, "password": "Test@123456"})
    emp_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    # ===== 1. Excel 导出 =====
    section("Excel 导出")
    r = c.get("/questions/export", headers=admin_h)
    ok("导出 xlsx 200", r.status_code == 200 and r.headers.get("content-type", "").startswith(
        "application/vnd.openxmlformats"), f"ct={r.headers.get('content-type')}")
    ok("导出文件非空", len(r.content) > 1000, f"bytes={len(r.content)}")
    # 模板
    r = c.get("/questions/export/template", headers=admin_h)
    ok("模板下载 200", r.status_code == 200 and len(r.content) > 500)

    # ===== 2. Excel 导入 =====
    section("Excel 导入")
    # 构造合法 xlsx：2 道题
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["type", "content", "options", "answer", "analysis", "knowledge_point", "difficulty"])
    ws.append(["SINGLE", f"导入测试-{ts}-安全带使用", "A. 系挂牢固|B. 随意|C. 不系", "A",
               "解析：必须系挂牢固。", "高处作业", "EASY"])
    ws.append(["JUDGE", f"导入测试-{ts}-雨天作业", "", "B",
               "解析：雨天应停止露天高处作业。", "高处作业", "MEDIUM"])
    buf = io.BytesIO()
    wb.save(buf)
    r = c.post("/questions/import", files={"file": ("import.xlsx", buf.getvalue(),
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers=admin_h)
    d = r.json()["data"]
    ok("导入 2 题成功", r.status_code == 200 and d["imported"] == 2 and not d["errors"],
       f"imported={d.get('imported')} errors={d.get('errors')}")
    # 非法行：缺解析 + 非法题型
    wb2 = Workbook()
    ws2 = wb2.active
    ws2.append(["type", "content", "options", "answer", "analysis", "knowledge_point", "difficulty"])
    ws2.append(["XXX", "坏题", "", "A", "", "kp", "EASY"])       # 题型非法 + 解析缺失
    ws2.append(["SINGLE", "好题", "A. 一|B. 二", "A", "解析", "kp", "EASY"])  # 合法
    buf2 = io.BytesIO()
    wb2.save(buf2)
    r = c.post("/questions/import", files={"file": ("bad.xlsx", buf2.getvalue(), "application/octet-stream")},
               headers=admin_h)
    d = r.json()["data"]
    ok("非法行逐行报错（行2）", r.status_code == 200 and any(e["row"] == 2 for e in d["errors"]),
       f"errors={d.get('errors')}")
    ok("非法文件扩展名 400", c.post("/questions/import", files={"file": ("bad.txt", b"x", "text/plain")},
                                  headers=admin_h).status_code == 400)

    # ===== 3. 考试统计 / 错题本 =====
    section("考试统计 + 错题本")
    # 造一场考试：组卷（含 2 题）→ 发布 → 作答（故意答错一题）→ 交卷
    r = c.get("/questions", params={"status": "APPROVED", "page_size": 2}, headers=admin_h)
    qs = r.json()["data"]["items"]
    q1, q2 = qs[0]["id"], qs[1]["id"]
    r = c.post("/papers/manual", json={
        "name": f"统计卷-{ts}", "duration": 30, "total_score": 20, "pass_score": 12,
        "questions": [{"question_id": q1, "score": 10}, {"question_id": q2, "score": 10}]},
        headers=admin_h)
    pid = r.json()["data"]["id"]
    c.put(f"/papers/{pid}", json={"status": "PUBLISHED"}, headers=admin_h)
    r = c.post("/exams/start", json={"paper_id": pid}, headers=emp_h)
    rec_id = r.json()["data"]["record_id"]
    sheet = r.json()["data"]
    # 看题目脱敏信息（无答案）——用错误答案交卷（全选 A，正确答案未必是 A → 至少错 1 题）
    answers = [{"question_id": q["id"], "user_answer": "A"} for q in sheet["questions"]]
    r = c.post(f"/exams/{rec_id}/submit", json={"answers": answers}, headers=emp_h)
    ok("交卷成功", r.json()["code"] == 200)
    # 统计（本人）
    r = c.get("/exams/stats", headers=emp_h)
    d = r.json()["data"]
    ok("本人统计含 total_exams/pass_rate", "total_exams" in d and "pass_rate" in d and "wrong_top" in d,
       f"total={d.get('total_exams')} rate={d.get('pass_rate')}")
    # 错题本
    r = c.get("/exams/wrong-book", headers=emp_h)
    d = r.json()["data"]
    ok("错题本返回明细", r.status_code == 200 and isinstance(d.get("items"), list),
       f"total={d.get('total')} items={len(d.get('items', []))}")
    ok("错题本含正确答案/解析", all("correct_answer" in i and "analysis" in i for i in d.get("items", [])))
    # 员工请求全站统计：安全设计为「静默降级为本人统计」（不暴露角色探测信号）
    r = c.get("/exams/stats", params={"all": 1}, headers=emp_h)
    d = r.json()["data"]
    ok("员工请求 all=1 → 静默返回本人统计（不报错不泄露全站）",
       r.status_code == 200 and d.get("total_exams") == 1, f"total={d.get('total_exams')}")
    # ADMIN 全站统计
    r = c.get("/exams/stats", params={"all": 1}, headers=admin_h)
    ok("ADMIN 全站统计 200", r.status_code == 200 and r.json()["code"] == 200)

    # ===== 4. 审计日志查询 =====
    section("审计日志查询")
    r = c.get("/logs", headers=admin_h)
    d = r.json()["data"]
    ok("日志列表 200 + 分页", r.status_code == 200 and d["total"] >= 5, f"total={d.get('total')}")
    ok("日志含登录/导入/交卷动作",
       any(i["action"] == "login" for i in d["items"]) and
       any(i["action"] == "question_import" for i in d["items"]) and
       any(i["action"] == "exam_submit" for i in d["items"]),
       f"actions={sorted({i['action'] for i in d['items']})}")
    r = c.get("/logs", params={"action": "exam_submit"}, headers=admin_h)
    ok("按 action 筛选", r.status_code == 200 and all(i["action"] == "exam_submit" for i in r.json()["data"]["items"]))
    r = c.get("/logs", params={"keyword": "imported"}, headers=admin_h)
    ok("按关键字筛选（detail=imported）", r.status_code == 200 and len(r.json()["data"]["items"]) >= 1)
    r = c.get("/logs", headers=emp_h)
    ok("员工查日志 403", r.status_code == 403, f"got {r.status_code}")

    c.close()
    print(f"\n{'='*60}\n结果：PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("Excel/统计/错题本/日志 验证全部通过 ✅")


if __name__ == "__main__":
    main()
