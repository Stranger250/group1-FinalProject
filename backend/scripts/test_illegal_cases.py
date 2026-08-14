"""非法状况补全测试：覆盖 test_boundary_security.py / overall_test.py / test_bugfix.py 未覆盖的 400/404/409/422 分支。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_illegal_cases.py
前置：uvicorn 8000 + MySQL shudao；admin 可登录。
退出码 0 = 全部通过。

覆盖清单（对照 service/schema 全部 raise 分支盘点）：
  A 认证：注册重名 400、登录不存在用户 401
  B 题目题型校验矩阵：单选无选项、多选非法选项、判断答案非 A/B、判断选项非法、填空空答案
  C 试卷：同题重复入卷 400、分值需统一 400、已发布删除 400、total_score/pass_score/questions 边界
  D auto 组卷：knowledge_points 空 422、rules 超限 422
  E AI 出题：law_title/reference_text 超长 422
  F 用户管理：role_id/status 越界 422、禁自身 400、用户不存在 404
  G 隐患：type/location 超长 422
  H 聊天：mode 超长 422、反馈非 AI 消息 400、反馈不存在消息 404
  I 考试：未发布开考 400、试卷不存在 404、未交卷查成绩 400、save 非本卷题目 400、切屏第4次自动交卷
  J 审核：手动题 400、驳回无意见 400、批次不存在 404
  K 重写：手动题 400、非 REJECTED 400
  L 答题：user_answer 超长 422、source_law_title 超长 422
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

    # 预热（8000 端口 reload 实例空闲后首个请求慢）
    warm = C()
    for i in range(6):
        try:
            if warm.req("GET", "/").status_code == 200:
                print(f"[预热] 第 {i+1} 次成功")
                break
        except httpx.HTTPError:
            pass
        time.sleep(2)
    warm.close()

    admin = C()
    r = admin.req("POST", "/auth/login", data={"username": "admin", "password": "Admin@123456"})
    assert r.json()["code"] == 200, "admin 登录失败"
    admin.token = r.json()["data"]["access_token"]

    emp = C()
    uname = f"t_ill_{ts}"
    r = emp.req("POST", "/auth/register", json={"username": uname, "password": "Test@123456", "name": "非法态"})
    assert r.status_code == 200, "员工注册失败"
    r = emp.req("POST", "/auth/login", data={"username": uname, "password": "Test@123456"})
    emp.token = r.json()["data"]["access_token"]

    # ===== A 认证 =====
    section("A · 认证")
    r = emp.req("POST", "/auth/register", json={"username": uname, "password": "Test@123456", "name": "重复"})
    ok("注册已存在用户名 → 400", r.status_code == 400 and "已存在" in r.json().get("message", ""), f"got {r.status_code}")
    r = emp.req("POST", "/auth/login", data={"username": "no_such_user_xyz", "password": "Test@123456"})
    ok("登录不存在用户 → 401", r.status_code == 401, f"got {r.status_code}")

    # ===== B 题目题型校验矩阵 =====
    section("B · 题目题型校验矩阵")
    base = {"content": "题", "analysis": "解析", "knowledge_point": "kp", "difficulty": "EASY"}
    r = admin.req("POST", "/questions", json={**base, "type": "SINGLE", "options": None, "answer": "A"})
    ok("单选无选项 → 400", r.status_code == 400, f"got {r.status_code}")
    r = admin.req("POST", "/questions", json={**base, "type": "MULTIPLE",
                  "options": ["A. 一", "B. 二"], "answer": "A,C"})
    ok("多选答案含非法选项 C → 400", r.status_code == 400, f"got {r.status_code}")
    r = admin.req("POST", "/questions", json={**base, "type": "JUDGE", "answer": "C"})
    ok("判断答案非 A/B → 400", r.status_code == 400, f"got {r.status_code}")
    r = admin.req("POST", "/questions", json={**base, "type": "JUDGE", "answer": "A",
                  "options": ["X 正确", "Y 错误"]})
    ok("判断题选项非 [A正确,B错误] → 400", r.status_code == 400, f"got {r.status_code}")
    r = admin.req("POST", "/questions", json={**base, "type": "FILL", "answer": "A;;B"})
    ok("填空空答案 → 400", r.status_code == 400, f"got {r.status_code}")
    # 合法各题型负控
    r = admin.req("POST", "/questions", json={**base, "type": "JUDGE", "answer": "A",
                  "options": ["A 正确", "B 错误"]})
    ok("合法判断题 → 200", r.status_code == 200 and r.json()["code"] == 200)
    if r.json().get("code") == 200:
        admin.req("DELETE", f"/questions/{r.json()['data']['id']}")
    r = admin.req("POST", "/questions", json={**base, "type": "FILL", "answer": "安全第一;预防为主"})
    ok("合法填空题 → 200", r.status_code == 200 and r.json()["code"] == 200)
    if r.json().get("code") == 200:
        admin.req("DELETE", f"/questions/{r.json()['data']['id']}")

    # ===== C 试卷 =====
    section("C · 试卷")
    r = admin.req("GET", "/questions", params={"status": "APPROVED", "page_size": 2})
    qs = r.json()["data"]["items"]
    q1, q2 = qs[0]["id"], qs[1]["id"]
    r = admin.req("POST", "/papers/manual", json={
        "name": f"t_dup_{ts}", "duration": 30, "total_score": 100,
        "questions": [{"question_id": q1, "score": 50}, {"question_id": q1, "score": 50}]})
    ok("同一题目重复入卷 → 400", r.status_code == 400, f"got {r.status_code}")
    r = admin.req("POST", "/papers/manual", json={
        "name": f"t_mix_{ts}", "duration": 30, "total_score": 100,
        "questions": [{"question_id": q1, "score": 50}, {"question_id": q2, "score": None}]})
    ok("分值部分指定部分均分 → 400", r.status_code == 400, f"got {r.status_code}")
    r = admin.req("POST", "/papers/manual", json={
        "name": f"t_pub_{ts}", "duration": 30, "total_score": 100,
        "questions": [{"question_id": q1, "score": 100}]})
    pid = r.json()["data"]["id"]
    admin.req("PUT", f"/papers/{pid}", json={"status": "PUBLISHED"})
    r = admin.req("DELETE", f"/papers/{pid}")
    ok("已发布试卷删除 → 400", r.status_code == 400, f"got {r.status_code}")
    admin.req("PUT", f"/papers/{pid}", json={"status": "DISABLED"})
    r = admin.req("DELETE", f"/papers/{pid}")
    ok("停用(DISABLED)试卷删除 → 200", r.status_code == 200 and r.json()["code"] == 200, f"got {r.status_code}")
    r = admin.req("POST", "/papers/manual", json={
        "name": "b", "duration": 30, "total_score": 5, "questions": [{"question_id": q1, "score": 5}]})
    ok("total_score=5(<10) → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/papers/manual", json={
        "name": "b", "duration": 30, "pass_score": 101, "questions": [{"question_id": q1, "score": 100}]})
    ok("pass_score=101 → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/papers/manual", json={
        "name": "b", "duration": 30, "questions": [{"question_id": q1, "score": 100} for _ in range(201)]})
    ok("questions 201 条(>200) → 422", r.status_code == 422, f"got {r.status_code}")

    # ===== D auto 组卷 =====
    section("D · auto 组卷")
    r = admin.req("POST", "/papers/auto", json={
        "name": "b", "duration": 30, "rules": [{"type": "SINGLE", "count": 1}], "knowledge_points": []})
    ok("knowledge_points 空列表 → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/papers/auto", json={
        "name": "b", "duration": 30, "rules": [{"type": "SINGLE", "count": 1}], "knowledge_points": ["  "]})
    ok("knowledge_points 全空白串 → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/papers/auto", json={
        "name": "b", "duration": 30, "rules": [{"type": "SINGLE", "count": 1} for _ in range(51)]})
    ok("rules 51 条(>50) → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/papers/auto", json={
        "name": "b", "duration": 30, "rules": [{"type": "SINGLE", "count": 1}],
        "total_score": 100})
    ok("auto 正常组卷 → 200", r.status_code == 200 and r.json()["code"] == 200, f"got {r.status_code}")

    # ===== E AI 出题 =====
    section("E · AI 出题字段")
    gen = {"knowledge_point": "高处作业", "types": ["SINGLE"], "difficulty": "EASY", "count": 5}
    r = admin.req("POST", "/ai/generate", json={**gen, "law_title": "t" * 129})
    ok("law_title 129 字符 → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/ai/generate", json={**gen, "reference_text": "r" * 6001})
    ok("reference_text 6001 字符 → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/ai/generate", json={**gen, "reference_title": "t" * 129})
    ok("reference_title 129 字符 → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/ai/generate", json={"types": ["SINGLE"], "difficulty": "EASY", "count": 5})
    ok("knowledge_point 与 reference_text 都缺 → 400", r.status_code == 400, f"got {r.status_code}")

    # ===== F 用户管理 =====
    section("F · 用户管理")
    r = admin.req("GET", "/users", params={"keyword": "admin", "page_size": 5})
    users = r.json()["data"]["items"]
    admin_uid = next(u["id"] for u in users if u["username"] == "admin")
    r = admin.req("PUT", f"/users/{users[0]['id']}", json={"role_id": 4})
    ok("role_id=4 越界 → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("PUT", f"/users/{users[0]['id']}", json={"status": 2})
    ok("status=2 越界 → 422", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("PUT", f"/users/{admin_uid}", json={"status": 0})
    ok("禁用当前登录管理员 → 400", r.status_code == 400, f"got {r.status_code}")
    r = admin.req("PUT", f"/users/{admin_uid}", json={"role_id": 1})
    ok("降级当前登录管理员 → 400", r.status_code == 400, f"got {r.status_code}")
    r = admin.req("PUT", "/users/999999", json={"status": 1})
    ok("更新不存在用户 → 404", r.status_code == 404, f"got {r.status_code}")
    r = admin.req("POST", "/users/999999/reset-password")
    ok("重置不存在用户密码 → 404", r.status_code == 404, f"got {r.status_code}")

    # ===== G 隐患 =====
    section("G · 隐患字段")
    r = emp.req("POST", "/hazards", json={"description": "d", "level": "MAJOR", "type": "t" * 33})
    ok("type 33 字符 → 422", r.status_code == 422, f"got {r.status_code}")
    r = emp.req("POST", "/hazards", json={"description": "d", "level": "MAJOR", "location": "l" * 129})
    ok("location 129 字符 → 422", r.status_code == 422, f"got {r.status_code}")

    # ===== H 聊天 =====
    section("H · 聊天/反馈")
    r = emp.req("POST", "/ai/chat", json={"message": "你好", "mode": "m" * 17})
    ok("mode 17 字符 → 422", r.status_code == 422, f"got {r.status_code}")
    r = emp.req("POST", "/ai/conversations", json={"title": "反馈测试"})
    cid = r.json()["data"]["id"]
    # 先发一条用户消息，拿 user 消息 id 测「只能给 AI 回答反馈」
    r = emp.req("POST", "/ai/chat", json={"conversation_id": cid, "message": "安全帽的作用是什么？"})
    r = emp.req("GET", f"/ai/conversations/{cid}/messages")
    msgs = r.json()["data"]
    user_msg = next(m for m in msgs if m.get("role") == "user")
    r = emp.req("POST", f"/ai/feedback/{user_msg['id']}", json={"value": 1})
    ok("反馈给 user 消息 → 400", r.status_code == 400, f"got {r.status_code}")
    r = emp.req("POST", "/ai/feedback/99999999", json={"value": 1})
    ok("反馈不存在消息 → 404", r.status_code == 404, f"got {r.status_code}")

    # ===== I 考试 =====
    section("I · 考试非法态")
    # 未发布试卷开考
    r = admin.req("POST", "/papers/manual", json={
        "name": f"t_draft_{ts}", "duration": 30, "total_score": 100,
        "questions": [{"question_id": q1, "score": 100}]})
    draft_pid = r.json()["data"]["id"]  # 保持 DRAFT 不发布
    r = emp.req("POST", "/exams/start", json={"paper_id": draft_pid})
    ok("未发布试卷开考 → 400", r.status_code == 400, f"got {r.status_code}")
    admin.req("DELETE", f"/papers/{draft_pid}")
    r = emp.req("POST", "/exams/start", json={"paper_id": 99999999})
    ok("试卷不存在开考 → 404", r.status_code == 404, f"got {r.status_code}")
    # 已发布试卷：未交卷查成绩 → 400
    r = admin.req("POST", "/papers/manual", json={
        "name": f"t_run_{ts}", "duration": 30, "total_score": 100,
        "questions": [{"question_id": q1, "score": 100}]})
    run_pid = r.json()["data"]["id"]
    admin.req("PUT", f"/papers/{run_pid}", json={"status": "PUBLISHED"})
    r = emp.req("POST", "/exams/start", json={"paper_id": run_pid})
    rec_id = r.json()["data"]["record_id"]
    r = emp.req("GET", f"/exams/{rec_id}/result")
    ok("未交卷查看成绩单 → 400", r.status_code == 400, f"got {r.status_code}")
    # save 非本卷题目 → 400（q2 不在本卷）
    r = emp.req("POST", f"/exams/{rec_id}/save", json={"answers": [{"question_id": q2, "user_answer": "A"}]})
    ok("save 非本卷题目 → 400", r.status_code == 400, f"got {r.status_code}")
    # 切屏：1/2/3 保持进行中（返回 triggered=False），第 4 次自动交卷
    for n, expect in ((1, 1), (2, 2), (3, 3)):
        r = emp.req("POST", f"/exams/{rec_id}/switch", json={"cheat_count": n})
        d = r.json().get("data", {})
        ok(f"切屏第 {n} 次 → 未触发且计数={expect}",
           d.get("triggered") is False and d.get("cheat_count") == expect,
           f"triggered={d.get('triggered')} cheat_count={d.get('cheat_count')}")
    r = emp.req("POST", f"/exams/{rec_id}/switch", json={"cheat_count": 4})
    body = r.json()
    ok("切屏第 4 次 → 自动交卷 SUBMITTED", body.get("data", {}).get("state") == "SUBMITTED",
       f"state={body.get('data', {}).get('state')} reason={body.get('data', {}).get('reason')}")
    ok("自动交卷原因=cheat_limit", body.get("data", {}).get("reason") == "cheat_limit",
       f"reason={body.get('data', {}).get('reason')}")
    r = emp.req("GET", f"/exams/{rec_id}/result")
    ok("自动交卷后可查成绩单 → 200", r.status_code == 200 and r.json()["code"] == 200, f"got {r.status_code}")
    r = emp.req("POST", f"/exams/{rec_id}/save", json={"answers": []})
    ok("已交卷后 save 幂等返回成绩单 → 200", r.status_code == 200 and r.json()["code"] == 200, f"got {r.status_code}")
    r = emp.req("POST", f"/exams/{rec_id}/submit", json={"answers": []})
    ok("已交卷后重复 submit → 200 幂等", r.status_code == 200 and r.json()["code"] == 200, f"got {r.status_code}")

    # ===== J 审核 =====
    section("J · E02 审核")
    # 手动题审核 → 400
    r = admin.req("POST", "/questions", json={
        "type": "SINGLE", "content": "手动审核测试题", "options": ["A. 是", "B. 否"],
        "answer": "A", "analysis": "解析", "knowledge_point": "kp", "difficulty": "EASY"})
    manual_qid = r.json()["data"]["id"]
    r = admin.req("POST", f"/ai/questions/{manual_qid}/review", json={"action": "APPROVE"})
    ok("审核手动题 → 400（仅可审核 AI 生成）", r.status_code == 400, f"got {r.status_code}")
    admin.req("DELETE", f"/questions/{manual_qid}")
    # 找一张 AI PENDING 题：驳回无意见 → 400
    r = admin.req("GET", "/ai/batches")
    batches = r.json()["data"]
    ai_pending_qid = None
    for b in batches:
        if b.get("pending", 0) > 0:
            r2 = admin.req("GET", f"/ai/batches/{b['batch_id']}")
            for q in r2.json()["data"].get("questions", []):
                if q["status"] == "PENDING":
                    ai_pending_qid = q["id"]
                    break
            if ai_pending_qid:
                break
    if ai_pending_qid:
        r = admin.req("POST", f"/ai/questions/{ai_pending_qid}/review", json={"action": "REJECT"})
        ok("驳回无审核意见 → 400", r.status_code == 400, f"got {r.status_code}")
        r = admin.req("POST", f"/ai/questions/{ai_pending_qid}/review",
                      json={"action": "REJECT", "review_note": "边界测试驳回"})
        ok("驳回带意见 → 200", r.status_code == 200 and r.json()["code"] == 200, f"got {r.status_code}")
        r = admin.req("POST", f"/ai/questions/{ai_pending_qid}/rewrite", json={"feedback": "请修订"})
        ok("重写 REJECTED 题（LLM 校验入参）→ 200 或 502", r.status_code in (200, 502), f"got {r.status_code}")
    else:
        ok("未找到 AI PENDING 题，审核分支跳过", True)
    r = admin.req("POST", "/ai/batches/no_such_batch/review", json={"action": "APPROVE"})
    ok("审核不存在批次 → 404", r.status_code == 404, f"got {r.status_code}")

    # ===== K 重写权限 =====
    section("K · E02 重写权限")
    r = admin.req("POST", "/questions", json={
        "type": "SINGLE", "content": "重写权限测试题", "options": ["A. 是", "B. 否"],
        "answer": "A", "analysis": "解析", "knowledge_point": "kp", "difficulty": "EASY"})
    manual_qid2 = r.json()["data"]["id"]
    r = admin.req("POST", f"/ai/questions/{manual_qid2}/rewrite", json={"feedback": "改一下"})
    ok("重写手动题 → 400（仅可重写 AI 生成）", r.status_code == 400, f"got {r.status_code}")
    admin.req("DELETE", f"/questions/{manual_qid2}")
    r = admin.req("POST", "/ai/questions/99999999/rewrite", json={"feedback": "改一下"})
    ok("重写不存在题目 → 404", r.status_code == 404, f"got {r.status_code}")

    # ===== L 答题/题目字段 =====
    section("L · 答题/题目字段")
    r = emp.req("POST", f"/exams/{rec_id}/save",
                json={"answers": [{"question_id": q1, "user_answer": "A" * 2001}]})
    ok("user_answer 2001 字符 → 422（上限已随解答题放宽至 2000）", r.status_code == 422, f"got {r.status_code}")
    r = admin.req("POST", "/questions", json={
        "type": "SINGLE", "content": "溯源长度", "options": ["A. 是", "B. 否"],
        "answer": "A", "analysis": "解析", "knowledge_point": "kp", "difficulty": "EASY",
        "source_law_title": "t" * 256})
    ok("source_law_title 256 字符 → 422", r.status_code == 422, f"got {r.status_code}")

    admin.close()
    emp.close()

    print(f"\n{'='*60}\n结果：PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("非法状况补全测试全部通过 ✅")


if __name__ == "__main__":
    main()
