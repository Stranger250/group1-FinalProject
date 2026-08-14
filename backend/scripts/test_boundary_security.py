"""边界测试 + 安全测试（针对 PRD/TEST_PLAN 边界与安全用例）。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_boundary_security.py
前置：uvicorn 已在 127.0.0.1:8000；MySQL shudao 库；admin/Admin@123456 可登录。
退出码 0 = 全部通过。

覆盖：
  边界：分页上限、注册/资料/改密字段长度与格式、题目字段、试卷时长/分值、
        隐患字段、聊天消息/标题/反馈、考试参数、AI 出题 count/types；
  安全：越权矩阵（401/403/404 掩码）、篡改 token、上传白名单/大小/穿越、
        敏感词拦截、SQL 注入探测、XSS 存储原样、头像/文档上传。
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime

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


class C:
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
    tag = f"BS{ts}"

    # 预热：8000 端口 uvicorn --reload 空闲后首个请求可能冷启动（~17s），预热到稳定再测
    warm = C()
    for i in range(6):
        try:
            if warm.req("GET", "/").status_code == 200:
                print(f"[预热] 第 {i+1} 次探测成功，开始测试")
                break
        except httpx.HTTPError:
            pass
        time.sleep(2)
    warm.close()

    admin = C()
    r = admin.req("POST", "/auth/login", data={"username": "admin", "password": "Admin@123456"})
    assert r.json()["code"] == 200, "admin 登录失败"
    admin.token = r.json()["data"]["access_token"]

    # 独立测试员工 A / B（B 用于越权与 404 掩码）
    empA = C()
    r = empA.req("POST", "/auth/register", json={"username": f"t_bsa_{ts}", "password": "Test@123456", "name": "边界A"})
    ok("注册测试员工A", r.status_code == 200 and r.json()["code"] == 200)
    empA_uid = r.json()["data"]["id"]
    r = empA.req("POST", "/auth/login", data={"username": f"t_bsa_{ts}", "password": "Test@123456"})
    empA.token = r.json()["data"]["access_token"]

    empB = C()
    r = empB.req("POST", "/auth/register", json={"username": f"t_bsb_{ts}", "password": "Test@123456", "name": "边界B"})
    ok("注册测试员工B", r.status_code == 200 and r.json()["code"] == 200)
    r = empB.req("POST", "/auth/login", data={"username": f"t_bsb_{ts}", "password": "Test@123456"})
    empB.token = r.json()["data"]["access_token"]

    # ================= 边界测试 =================
    section("边界 · 分页参数")
    for url in ("/questions", "/papers", "/hazards", "/exams/papers", "/exams/records", "/users"):
        r = admin.req("GET", url, params={"page": 0})
        ok(f"{url} page=0 → 422", r.status_code == 422, f"got {r.status_code}")
        r = admin.req("GET", url, params={"page": 100001})
        ok(f"{url} page=100001 → 422", r.status_code == 422, f"got {r.status_code}")
        r = admin.req("GET", url, params={"page_size": 0})
        ok(f"{url} page_size=0 → 422", r.status_code == 422, f"got {r.status_code}")
        r = admin.req("GET", url, params={"page_size": 101})
        ok(f"{url} page_size=101 → 422", r.status_code == 422, f"got {r.status_code}")

    section("边界 · 注册字段")
    r = empA.req("POST", "/auth/register", json={"username": "ab", "password": "Test@123456", "name": "x"})
    ok("username 2 字符 → 422", r.status_code == 422, f"got {r.status_code}")
    r = empA.req("POST", "/auth/register", json={"username": "a" * 65, "password": "Test@123456", "name": "x"})
    ok("username 65 字符 → 422", r.status_code == 422)
    r = empA.req("POST", "/auth/register", json={"username": f"t_bsx_{ts}", "password": "12345", "name": "x"})
    ok("password 5 字符 → 422", r.status_code == 422)
    r = empA.req("POST", "/auth/register", json={"username": f"t_bsx2_{ts}", "password": "测" * 30, "name": "x"})
    ok("password 90 汉字(>72字节) → 422", r.status_code == 422, f"got {r.status_code}")
    r = empA.req("POST", "/auth/register", json={"username": f"t_bsx3_{ts}", "password": "Test@123456", "name": ""})
    ok("name 空 → 422", r.status_code == 422)
    r = empA.req("POST", "/auth/register", json={"username": f"t_bsx4_{ts}", "password": "Test@123456", "name": "x", "phone": "1" * 21})
    ok("phone 21 字符 → 422", r.status_code == 422)

    section("边界 · 资料/改密")
    r = empA.req("PUT", "/auth/profile", json={"name": "边界A", "phone": "abc123"})
    ok("phone 非数字 → 422", r.status_code == 422, f"got {r.status_code}")
    r = empA.req("PUT", "/auth/profile", json={"name": "边界A", "email": "not-an-email"})
    ok("email 格式错误 → 422", r.status_code == 422)
    r = empA.req("PUT", "/auth/password", json={"old_password": "wrong", "new_password": "NewPass@123"})
    ok("改密原密码错误 → 400", r.status_code == 400)
    r = empA.req("PUT", "/auth/password", json={"old_password": "Test@123456", "new_password": "Test@123456"})
    ok("改密新旧相同 → 400", r.status_code == 400)
    r = empA.req("PUT", "/auth/password", json={"old_password": "Test@123456", "new_password": "12345"})
    ok("改密新密码 5 字符 → 422", r.status_code == 422)

    section("边界 · 题目字段")
    bad_q = {"type": "SINGLE", "content": "", "options": ["A. 是", "B. 否"], "answer": "A",
             "analysis": "解析", "knowledge_point": "kp", "difficulty": "EASY"}
    r = admin.req("POST", "/questions", json=bad_q)
    ok("content 空 → 422", r.status_code == 422)
    bad_q["content"] = "题目"
    # answer 上限已随解答题放宽至 2000（原 64 上限失效）：65 字符合法，2001 字符越界
    bad_q["answer"] = "A" * 2001
    r = admin.req("POST", "/questions", json=bad_q)
    ok("answer 2001 字符 → 422", r.status_code == 422)
    bad_q["answer"] = "A"
    bad_q["analysis"] = ""
    r = admin.req("POST", "/questions", json=bad_q)
    ok("analysis 空 → 422", r.status_code == 422)
    bad_q["analysis"] = "解析"
    bad_q["knowledge_point"] = "k" * 129
    r = admin.req("POST", "/questions", json=bad_q)
    ok("knowledge_point 129 字符 → 422", r.status_code == 422)
    bad_q["knowledge_point"] = "kp"
    bad_q["answer"] = "Z"
    r = admin.req("POST", "/questions", json=bad_q)
    ok("单选答案不在选项 → 400", r.status_code == 400, f"got {r.status_code}")
    bad_q["answer"] = "A"
    r = admin.req("POST", "/questions", json=bad_q)
    ok("合法题目 → 200", r.status_code == 200 and r.json()["code"] == 200)
    qid = r.json()["data"]["id"]
    # 清理
    admin.req("DELETE", f"/questions/{qid}")

    section("边界 · 试卷")
    r = admin.req("POST", "/papers/manual", json={
        "name": "b", "duration": 45, "pass_score": 60, "questions": [{"question_id": 39, "score": 100}]})
    ok("duration=45（非30/60/90）→ 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/papers/manual", json={
        "name": "b", "duration": 30, "pass_score": 120, "total_score": 100, "questions": [{"question_id": 39, "score": 100}]})
    ok("pass_score>total_score → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/papers/manual", json={"name": "b", "duration": 30, "questions": []})
    ok("questions 空列表 → 422", r.status_code == 422)
    r = admin.req("POST", "/papers/manual", json={
        "name": "b", "duration": 30, "total_score": 100, "questions": [{"question_id": 39, "score": 50}]})
    ok("题目分值之和≠总分 → 400", r.status_code == 400, f"got {r.status_code}")
    r = admin.req("POST", "/papers/manual", json={
        "name": "b", "duration": 30, "total_score": 100, "questions": [{"question_id": 39, "score": 501}]})
    ok("单题分值 501 > 500 → 422", r.status_code == 422, f"got {r.status_code}")

    section("边界 · 隐患")
    r = empA.req("POST", "/hazards", json={"description": "", "level": "MAJOR"})
    ok("description 空 → 422", r.status_code == 422)
    r = empA.req("POST", "/hazards", json={"description": "d" * 2001, "level": "MAJOR"})
    ok("description 2001 字符 → 422", r.status_code == 422)
    r = empA.req("POST", "/hazards", json={"description": "d", "level": "MAJOR", "title": "t" * 129})
    ok("title 129 字符 → 422", r.status_code == 422)
    r = empA.req("POST", "/hazards", json={"description": "d", "level": "SUPER"})
    ok("level 非法枚举 → 422", r.status_code == 422)
    r = empA.req("POST", "/hazards", json={"description": "d", "level": "MAJOR", "images": [f"/uploads/20260814/{i}.jpg" for i in range(10)]})
    ok("images 10 张(>9) → 422", r.status_code == 422, f"got {r.status_code}")
    r = empA.req("POST", "/hazards", json={"description": "d", "level": "MAJOR", "extra_field": "x"})
    ok("extra 字段(extra=forbid) → 422", r.status_code == 422, f"got {r.status_code}")

    section("边界 · 聊天/反馈")
    r = empA.req("POST", "/ai/chat", json={"message": ""})
    ok("chat message 空 → 422", r.status_code == 422)
    r = empA.req("POST", "/ai/chat", json={"message": "m" * 2001})
    ok("chat message 2001 字符 → 422", r.status_code == 422)
    r = empA.req("POST", "/ai/conversations", json={"title": "t" * 65})
    ok("会话标题 65 字符 → 422", r.status_code == 422)
    r = empA.req("POST", "/ai/feedback/1", json={"value": 2})
    ok("feedback value=2 → 422", r.status_code == 422)
    r = empA.req("POST", "/ai/feedback/1", json={"value": 0.5})
    ok("feedback value=0.5 → 422", r.status_code == 422)

    section("边界 · 考试参数")
    r = empA.req("POST", "/exams/start", json={"paper_id": 0})
    ok("paper_id=0 → 422", r.status_code == 422)
    r = empA.req("POST", "/exams/1/switch", json={"cheat_count": -1})
    ok("cheat_count=-1 → 422", r.status_code == 422)
    r = empA.req("POST", "/exams/1/switch", json={"cheat_count": 100001})
    ok("cheat_count=100001 → 422", r.status_code == 422)
    r = empA.req("POST", "/exams/1/save", json={"answers": [{"question_id": i, "user_answer": "A"} for i in range(501)]})
    ok("answers 501 条(>500) → 422", r.status_code == 422, f"got {r.status_code}")
    r = empA.req("POST", "/exams/1/save", json={"answers": [{"question_id": 1, "user_answer": "A"}, {"question_id": 1, "user_answer": "B"}]})
    ok("重复 question_id 后值覆盖（200 或 404 均属校验通过）", r.status_code in (200, 404), f"got {r.status_code}")

    section("边界 · AI 出题参数")
    gen = {"knowledge_point": "高处作业", "types": ["SINGLE"], "difficulty": "EASY"}
    r = admin.req("POST", "/ai/generate", json={**gen, "count": 4})
    ok("count=4(<5) → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/ai/generate", json={**gen, "count": 51})
    ok("count=51(>50) → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/ai/generate", json={**gen, "count": 5, "types": []})
    ok("types 空列表 → 422", r.status_code == 422)
    r = admin.req("POST", "/ai/generate", json={**gen, "count": 5, "types": ["XXX"]})
    ok("types 非法枚举 → 422", r.status_code == 422)
    r = admin.req("POST", "/ai/generate", json={**gen, "count": 5, "difficulty": "HARDER"})
    ok("difficulty 非法枚举 → 422", r.status_code == 422)

    # ================= 安全测试 =================
    section("安全 · 认证（401）")
    anon = C()
    r = anon.req("GET", "/auth/me")
    ok("无 token → 401", r.status_code == 401)
    r = anon.req("GET", "/questions")
    ok("无 token 管理接口 → 401", r.status_code == 401)
    r = C("garbage.token.here").req("GET", "/auth/me")
    ok("伪 token → 401", r.status_code == 401)
    tampered = admin.token[:-2] + ("a" if admin.token[-2] != "a" else "b")
    r = C(tampered).req("GET", "/auth/me")
    ok("篡改签名 token → 401", r.status_code == 401)

    section("安全 · 越权（403）")
    r = empA.req("GET", "/questions")
    ok("员工访问题库 → 403", r.status_code == 403)
    r = empA.req("GET", "/papers")
    ok("员工访问试卷 → 403", r.status_code == 403)
    r = empA.req("POST", "/ai/generate", json={**gen, "count": 5})
    ok("员工 AI 出题 → 403", r.status_code == 403)
    r = empA.req("GET", "/ai/batches")
    ok("员工查看批次 → 403", r.status_code == 403)
    r = empA.req("GET", "/ai/stats")
    ok("员工查看统计 → 403", r.status_code == 403)
    r = empA.req("GET", "/users")
    ok("员工访问用户管理 → 403", r.status_code == 403)
    r = empA.req("POST", f"/hazards/{empA_uid}/close")
    ok("员工闭环隐患 → 403", r.status_code == 403)

    section("安全 · 404 掩码（防枚举）")
    # A 建会话与隐患
    r = empA.req("POST", "/ai/conversations", json={"title": "A的会话"})
    convA = r.json()["data"]["id"]
    r = empA.req("POST", "/hazards", json={"description": "A的隐患", "level": "GENERAL"})
    hazardA = r.json()["data"]["id"]
    # B 访问 A 的资源
    r = empB.req("GET", f"/ai/conversations/{convA}/messages")
    ok("B 查看 A 会话消息 → 404", r.status_code == 404, f"got {r.status_code}")
    r = empB.req("PUT", f"/ai/conversations/{convA}", json={"title": "hack"})
    ok("B 重命名 A 会话 → 404", r.status_code == 404)
    r = empB.req("DELETE", f"/ai/conversations/{convA}")
    ok("B 删除 A 会话 → 404", r.status_code == 404)
    # 隐患 H03 详情为 PRD 透明度设计（全员可见），非归属掩码——断言 200 属预期
    r = empB.req("GET", f"/hazards/{hazardA}")
    ok("B 查看 A 隐患详情 → 200（PRD 透明度设计，全员可见）", r.status_code == 200 and r.json()["code"] == 200, f"got {r.status_code}")
    r = empB.req("GET", "/hazards/99999999")
    ok("查看不存在的隐患 → 404", r.status_code == 404, f"got {r.status_code}")
    r = empB.req("GET", "/exams/1/result")
    ok("B 查看他人考试记录 → 404", r.status_code == 404)
    r = empA.req("GET", f"/ai/conversations/{convA}/messages")
    ok("A 自己查看会话正常 → 200", r.status_code == 200)

    section("安全 · 上传白名单/大小/穿越")
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    r = empA.req("POST", "/hazards/upload", files={"file": ("x.exe", b"mz", "application/octet-stream")})
    ok("上传 .exe → 400", r.status_code == 400)
    r = empA.req("POST", "/hazards/upload", files={"file": ("x.jpg", b"not-image", "image/jpeg")})
    ok("上传 .jpg 但内容非图片(MIME 白名单后仍存) → 200 或 400", r.status_code in (200, 400), f"got {r.status_code}")
    big = b"0" * (5 * 1024 * 1024 + 1)
    r = empA.req("POST", "/hazards/upload", files={"file": ("big.jpg", big, "image/jpeg")})
    ok("上传 >5MB → 400", r.status_code == 400, f"got {r.status_code}")
    r = empA.req("POST", "/hazards/upload", files={"file": ("..\\..\\evil.jpg", png, "image/jpeg")})
    body = r.json()
    url = body.get("data", {}).get("url", "")
    ok("路径穿越文件名 → 200 且 URL 无 ..", r.status_code == 200 and ".." not in url, f"url={url}")
    r = empA.req("POST", "/auth/avatar", files={"file": ("x.png", png, "image/png")})
    ok("头像上传 PNG → 200", r.status_code == 200 and r.json()["code"] == 200)
    r = empA.req("POST", "/auth/avatar", files={"file": ("x.txt", b"hi", "text/plain")})
    ok("头像上传 txt → 400", r.status_code == 400)

    section("安全 · 敏感词拦截")
    for word in ("造谣", "上访"):
        r = empA.req("POST", "/ai/chat", json={"message": f"我想了解一下{word}的相关规定"})
        ok(f"聊天含敏感词「{word}」→ 400", r.status_code == 400, f"got {r.status_code}")

    section("安全 · SQL 注入探测")
    r = empA.req("GET", "/hazards", params={"keyword": "' OR '1'='1"})
    ok("隐患 keyword SQL 注入 → 200 不报错", r.status_code == 200 and r.json()["code"] == 200)
    r = admin.req("GET", "/questions", params={"keyword": "1' UNION SELECT 1,2,3 --"})
    ok("题库 keyword SQL 注入 → 200 不报错", r.status_code == 200 and r.json()["code"] == 200)
    r = admin.req("GET", "/users", params={"keyword": "' OR 1=1 --"})
    ok("用户 keyword SQL 注入 → 200 不报错", r.status_code == 200 and r.json()["code"] == 200)
    r = admin.req("POST", "/auth/login", data={"username": "' OR '1'='1", "password": "' OR '1'='1"})
    ok("登录注入 → 401（未命中）", r.status_code == 401, f"got {r.status_code}")

    section("安全 · XSS 存储")
    xss_q = {"type": "SINGLE", "content": "<script>alert(1)</script>边界XSS题", "options": ["A. 是", "B. 否"],
             "answer": "A", "analysis": "<img src=x onerror=alert(1)>解析", "knowledge_point": "kp", "difficulty": "EASY"}
    r = admin.req("POST", "/questions", json=xss_q)
    saved = r.json().get("data", {}).get("content", "")
    ok("XSS 题干原样存储(前端 DOMPurify 负责净化) → 200", r.status_code == 200 and "<script>" in saved, f"got {r.status_code}")
    if r.json().get("code") == 200:
        admin.req("DELETE", f"/questions/{r.json()['data']['id']}")
    r = empA.req("POST", "/hazards", json={"description": "<script>alert(2)</script>隐患描述", "level": "MINOR"})
    ok("XSS 隐患描述存储 → 200", r.status_code == 200 and r.json()["code"] == 200)

    section("安全 · 引用/原文接口")
    r = empA.req("GET", "/ai/article")
    ok("/ai/article 缺 doc_id → 422", r.status_code == 422, f"got {r.status_code}")
    r = empA.req("GET", "/ai/article", params={"doc_id": "x"})
    ok("/ai/article 缺 article_no → 422", r.status_code == 422)
    r = empA.req("GET", "/ai/article", params={"doc_id": "no-such-doc", "article_no": "第一条"})
    ok("/ai/article 不存在 → 200 data=null 或 404", r.status_code in (200, 404), f"got {r.status_code}")
    r = empB.req("GET", "/ai/source/1")
    ok("B 查 A 消息引用 → 404 掩码", r.status_code == 404, f"got {r.status_code}")

    section("安全 · 禁用账号即时失效")
    r = admin.req("PUT", f"/users/{empA_uid}", json={"status": 0})
    ok("admin 禁用员工A → 200", r.status_code == 200 and r.json()["code"] == 200)
    r = empA.req("GET", "/auth/me")
    ok("禁用后旧 JWT 立即 401", r.status_code == 401, f"got {r.status_code}")
    r = empA.req("GET", "/hazards")
    ok("禁用后访问业务接口 401", r.status_code == 401)
    r = empA.req("POST", "/auth/login", data={"username": f"t_bsa_{ts}", "password": "Test@123456"})
    ok("禁用账号登录 → 403", r.status_code == 403, f"got {r.status_code}")

    admin.close()
    empA.close()
    empB.close()
    anon.close()

    print(f"\n{'='*60}\n结果：PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("边界测试 + 安全测试全部通过 ✅")


if __name__ == "__main__":
    main()
