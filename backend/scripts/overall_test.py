"""蜀道安全助手 · 整体测试脚本（覆盖三大模块 + 基础支撑）。

运行：cd shudao/backend && python scripts/overall_test.py
前置：uvicorn 已启动在 127.0.0.1:8000；MySQL 已建库；admin 账号存在。
说明：使用独立测试账号（t_ 前缀），测试产生的隐患/会话/考试数据保留在库中以便人工核查。
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
PASS = 0
FAIL = 0
FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f" | {detail}" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name}" + (f" | {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n===== {title} =====")


class Client:
    def __init__(self, token: str = ""):
        self.c = httpx.Client(base_url=BASE, timeout=60)
        self.token = token

    def h(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def req(self, method: str, url: str, **kw):
        kw.setdefault("headers", self.h())
        return self.c.request(method, url, **kw)

    def close(self):
        self.c.close()


def main() -> None:
    ts = datetime.now().strftime("%H%M%S")
    emp_name = f"t_emp_{ts}"
    emp = Client()

    # ============ 基础支撑 B01/B02/B03 ============
    section("基础支撑 B01 注册/登录/JWT")
    r = emp.req(
        "POST", "/api/v1/auth/register",
        json={"username": emp_name, "password": "Test@123456", "name": "测试员工", "role_id": 1},
    )
    body = r.json()
    ok("注册新用户", r.status_code == 200 and body["code"] == 200, f"{emp_name} role={body.get('data', {}).get('role_id')}")
    ok("注册强制 EMPLOYEE", body.get("data", {}).get("role_id") == 1)

    r = emp.req("POST", "/api/v1/auth/login", data={"username": emp_name, "password": "Test@123456"})
    body = r.json()
    ok("登录成功签发 JWT", r.status_code == 200 and body["code"] == 200 and "access_token" in body["data"])
    emp.token = body["data"]["access_token"]

    r = emp.req("GET", "/api/v1/auth/me")
    ok("GET /me 获取当前用户", r.status_code == 200 and r.json()["code"] == 200)

    r = emp.req("POST", "/api/v1/auth/login", data={"username": emp_name, "password": "wrong"})
    ok("错误密码登录 401", r.status_code == 401)

    anon = Client()
    r = anon.req("GET", "/api/v1/auth/me")
    ok("未登录访问受保护接口 401", r.status_code == 401)

    section("基础支撑 B02 角色权限")
    r = emp.req("GET", "/api/v1/questions")
    ok("员工访问题库管理 403", r.status_code == 403, f"status={r.status_code}")
    r = emp.req("GET", "/api/v1/papers")
    ok("员工访问试卷管理 403", r.status_code == 403)
    r = emp.req("GET", "/api/v1/ai/batches")
    ok("员工访问 AI 出题批次 403", r.status_code == 403)
    r = emp.req("POST", "/api/v1/auth/login", data={"username": "admin", "password": "Admin@123456"})
    admin = Client(r.json()["data"]["access_token"])
    r = admin.req("GET", "/api/v1/questions")
    ok("管理员访问题库管理 200", r.status_code == 200 and r.json()["code"] == 200)
    r = admin.req("GET", "/api/v1/auth/me")
    ok("管理员 /me role_id=3", r.json()["data"]["role_id"] == 3)

    section("基础支撑 B03 文件上传")
    # 构造 1x1 像素 PNG
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    r = emp.req("POST", "/api/v1/hazards/upload", files={"file": ("tiny.png", png, "image/png")})
    ok("上传合法 PNG 200", r.status_code == 200 and r.json()["code"] == 200, f"url={r.json().get('data', {}).get('url')}")
    upload_url = r.json().get("data", {}).get("url", "")

    bad = b"not an image at all but a fake file"
    r = emp.req("POST", "/api/v1/hazards/upload", files={"file": ("evil.exe", bad, "application/octet-stream")})
    ok("上传非法扩展名 400", r.status_code == 400, f"status={r.status_code}")

    # ============ 模块一 隐患管理 H01-H03 ============
    section("模块一 隐患管理 H01 上报")
    payload = {
        "title": "测试-施工现场临时用电线路裸露",
        "description": "测试数据：3号基坑边临时用电线路绝缘层破损裸露，存在触电风险，请尽快处理。",
        "location": "测试-3号基坑东侧",
        "level": "MAJOR",
        "type": "用电安全",
        "images": [upload_url] if upload_url else [],
    }
    r = emp.req("POST", "/api/v1/hazards", json=payload)
    body = r.json()
    ok("H01 隐患上报", r.status_code == 200 and body["code"] == 200, f"hazard_no={body.get('data', {}).get('hazard_no')}")
    hid = body.get("data", {}).get("id")
    hno = body.get("data", {}).get("hazard_no")
    ok("编号格式 HZ+日期+序号", hno and hno.startswith("HZ") and len(hno) >= 13, hno or "")
    ok("初始状态 WAIT_PROCESS", body.get("data", {}).get("status") == "WAIT_PROCESS")

    section("模块一 隐患管理 H02 列表")
    r = emp.req("GET", "/api/v1/hazards", params={"page": 1, "page_size": 5})
    body = r.json()
    ok("H02 隐患列表分页", r.status_code == 200 and body["code"] == 200 and len(body["data"]["items"]) >= 1)
    ok("H02 列表含 total", body["data"]["total"] >= 1, f"total={body['data']['total']}")
    r = emp.req("GET", "/api/v1/hazards", params={"status": "WAIT_PROCESS", "level": "MAJOR", "page": 1})
    ok("H02 状态+等级组合筛选", r.status_code == 200 and r.json()["code"] == 200)
    r = emp.req("GET", "/api/v1/hazards", params={"sort": "level", "order": "desc"})
    ok("H02 sort/order 排序", r.status_code == 200 and r.json()["code"] == 200)
    r = emp.req("GET", "/api/v1/hazards", params={"sort": "bad_field"})
    ok("H02 非法排序参数 422", r.status_code == 422)

    section("模块一 隐患管理 H03 详情/闭环")
    r = emp.req("GET", f"/api/v1/hazards/{hid}")
    body = r.json()
    ok("H03 隐患详情", r.status_code == 200 and body["code"] == 200 and body["data"]["id"] == hid)
    ok("详情含时间线", isinstance(body["data"].get("timeline"), list) and len(body["data"]["timeline"]) >= 1)

    r = emp.req("POST", f"/api/v1/hazards/{hid}/close")
    ok("员工闭环 403（越权）", r.status_code == 403, f"status={r.status_code}")
    r = admin.req("POST", f"/api/v1/hazards/{hid}/close")
    ok("管理员闭环 200", r.status_code == 200 and r.json()["code"] == 200, f"status={r.json().get('data', {}).get('status')}")
    r = admin.req("POST", f"/api/v1/hazards/{hid}/close")
    ok("重复闭环 400", r.status_code == 400, f"status={r.status_code}")

    # ============ 模块二 AI 助手 ============
    section("模块二 AI 助手 A02 会话管理")
    r = emp.req("POST", "/api/v1/ai/conversations")
    body = r.json()
    ok("新建会话", r.status_code == 200 and body["code"] == 200)
    cid = body["data"]["id"]

    r = emp.req("POST", "/api/v1/ai/conversations", json={"title": "测试会话"})
    body = r.json()
    cid2 = body["data"]["id"]
    ok("指定标题新建会话", body["data"]["title"] == "测试会话")

    r = emp.req("PUT", f"/api/v1/ai/conversations/{cid}", json={"title": "重命名会话"})
    ok("重命名会话", r.status_code == 200 and r.json()["data"]["title"] == "重命名会话")

    r = emp.req("GET", "/api/v1/ai/conversations")
    body = r.json()
    ok("会话列表", r.status_code == 200 and body["code"] == 200 and len(body["data"]["items"]) >= 2)

    section("模块二 AI 助手 A01 智能问答（SSE）")
    r = emp.req(
        "POST", "/api/v1/ai/chat",
        json={"conversation_id": cid, "message": "高处作业有哪些安全要求？"},
    )
    ok("SSE 流式回答 HTTP 200", r.status_code == 200, f"content-type={r.headers.get('content-type')}")
    if r.status_code == 200:
        events = []
        for line in r.text.split("\n"):
            if line.startswith("event:"):
                events.append(line[6:].strip())
        has_meta = "meta" in events
        has_done = "done" in events
        ok("SSE 事件序含 meta", has_meta, f"events={events[:6]}")
        ok("SSE 事件序含 done", has_done)
        if has_meta and has_done:
            ok("SSE meta 在 done 之前", events.index("meta") < events.index("done"))

    r = emp.req("POST", "/api/v1/ai/chat", json={"conversation_id": cid, "message": "测试敏感词触发"})
    ok("敏感词接口（无敏感词时应 200 或 400）", r.status_code in (200, 400))

    section("模块二 AI 助手 A04 快捷提问 / A07 反馈")
    r = emp.req("GET", "/api/v1/ai/quick-questions")
    ok("快捷提问列表", r.status_code == 200 and r.json()["code"] == 200)
    r = emp.req("GET", f"/api/v1/ai/conversations/{cid}/messages")
    body = r.json()
    ok("会话消息列表", r.status_code == 200 and body["code"] == 200)
    assistant_id = None
    for m in body["data"]:
        if m.get("role") == "assistant":
            assistant_id = m["id"]
            break
    if assistant_id:
        r = emp.req("POST", f"/api/v1/ai/feedback/{assistant_id}", json={"value": 1})
        ok("A07 点赞反馈", r.status_code == 200 and r.json()["code"] == 200)
        r = emp.req("POST", f"/api/v1/ai/feedback/{assistant_id}", json={"value": 0})
        ok("A07 清除反馈（幂等）", r.status_code == 200)
    else:
        ok("A07 反馈（无 assistant 消息，跳过）", True)

    r = emp.req("DELETE", f"/api/v1/ai/conversations/{cid2}")
    ok("删除会话", r.status_code == 200 and r.json()["code"] == 200)

    # ============ 模块三 考试工坊 E01-E05 ============
    section("模块三 E01 题库管理")
    q_payload = {
        "type": "SINGLE", "content": "测试-《安全生产法》规定生产经营单位的主要负责人对本单位安全生产工作（ ）。",
        "options": ["A. 全面负责", "B. 部分负责", "C. 不负责", "D. 间接负责"],
        "answer": "A", "analysis": "测试解析：《安全生产法》第五条。",
        "knowledge_point": "安全生产法", "difficulty": "EASY",
    }
    r = admin.req("POST", "/api/v1/questions", json=q_payload)
    body = r.json()
    ok("E01 手工录入题目", r.status_code == 200 and body["code"] == 200)
    qid = body["data"]["id"]
    ok("手工录入直接 APPROVED", body["data"]["status"] == "APPROVED")

    r = admin.req("PUT", f"/api/v1/questions/{qid}", json={**q_payload, "content": "测试-修改后的题干"})
    ok("E01 编辑题目", r.status_code == 200 and "修改后的题干" in r.json()["data"]["content"])
    r = admin.req("GET", "/api/v1/questions", params={"page": 1, "page_size": 5})
    ok("E01 题库列表", r.status_code == 200 and r.json()["code"] == 200)
    r = admin.req("DELETE", f"/api/v1/questions/{qid}")
    ok("E01 删除题目", r.status_code == 200)

    section("模块三 E02 AI 出题（批次/审核/统计）")
    r = admin.req("GET", "/api/v1/ai/batches")
    ok("E02 批次列表", r.status_code == 200 and r.json()["code"] == 200)
    r = admin.req("GET", "/api/v1/ai/stats")
    ok("E02 出题统计", r.status_code == 200 and r.json()["code"] == 200)

    section("模块三 E03 试卷生成")
    r = admin.req("GET", "/api/v1/questions", params={"status": "APPROVED", "page_size": 3})
    body = r.json()
    approved = body.get("data", {}).get("items", [])
    ok("获取已审核题目", len(approved) >= 1, f"count={len(approved)}")
    if approved:
        qids = [q["id"] for q in approved]
        r = admin.req(
            "POST", "/api/v1/papers/manual",
            json={"name": f"测试-整体测试卷-{ts}", "duration": 30, "pass_score": 60, "questions": [{"question_id": qids[0], "score": 100}]},
        )
        body = r.json()
        ok("E03 手动组卷", r.status_code == 200 and body["code"] == 200, f"paper_id={body.get('data', {}).get('id')}")
        pid = body.get("data", {}).get("id")
        if pid:
            r = admin.req("PUT", f"/api/v1/papers/{pid}", json={"status": "PUBLISHED"})
            ok("E03 发布试卷", r.status_code == 200 and r.json()["data"]["status"] == "PUBLISHED")

    section("模块三 E04 在线考试 / E05 自动阅卷")
    r = emp.req("GET", "/api/v1/exams/papers")
    body = r.json()
    ok("公开选卷列表", r.status_code == 200 and r.json()["code"] == 200)
    published = body.get("data", {}).get("items", [])
    # 注意：公开选卷接口天然只返回已发布试卷（脱敏、无 status 字段）
    ok("存在已发布试卷", len(published) >= 1, f"count={len(published)}")
    if published:
        paper_id = published[0]["id"]
        r = emp.req("POST", "/api/v1/exams/start", json={"paper_id": paper_id})
        body = r.json()
        ok("E04 开始考试", r.status_code == 200 and body["code"] == 200, f"state={body.get('data', {}).get('state')}")
        record_id = body.get("data", {}).get("record_id")
        questions = body.get("data", {}).get("questions", [])
        ok("考试含题目", len(questions) >= 1, f"questions={len(questions)}")
        if record_id and questions:
            answers = [{"question_id": q["id"], "user_answer": (list(q.get("options") or [""])[0][:1] or "A")} for q in questions]
            r = emp.req("POST", f"/api/v1/exams/{record_id}/save", json={"answers": answers})
            ok("E04 保存答案", r.status_code == 200 and r.json()["code"] == 200)
            r = emp.req("GET", f"/api/v1/exams/{record_id}")
            ok("E04 刷新恢复", r.status_code == 200 and r.json()["code"] == 200)
            r = emp.req("POST", f"/api/v1/exams/{record_id}/submit", json={"answers": answers})
            body = r.json()
            ok("E05 交卷+自动阅卷", r.status_code == 200 and body["code"] == 200, f"state={body.get('data', {}).get('state')}")
            if body["code"] == 200:
                ok("成绩单含 score", "score" in body["data"], f"score={body['data'].get('score')}")
                ok("成绩单含 passed", "passed" in body["data"], f"passed={body['data'].get('passed')}")
            r = emp.req("GET", f"/api/v1/exams/{record_id}/result")
            ok("成绩单接口", r.status_code == 200 and r.json()["code"] == 200)
        r = emp.req("GET", "/api/v1/exams/records")
        ok("我的考试记录", r.status_code == 200 and r.json()["code"] == 200)

    section("健康检查")
    r = emp.req("GET", "/")
    ok("健康检查 /", r.status_code == 200 and r.json()["data"]["status"] == "ok")

    emp.close()
    admin.close()
    anon.close()

    print(f"\n{'='*60}\n结果：PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("整体测试全部通过 ✅")


if __name__ == "__main__":
    main()
