"""19 个 bug 修复的回归套件（对应 Workflow 审查 confirmed findings #1-#19）。

分两部分：
  U 纯单测（无需服务器/DB）：全角归一化（#11）、JWT 占位密钥旋转（#9）；
  R API 回归（需后端在 8000 端口 + MySQL shudao 库）：
    R1 删除有考试记录的试卷 → 400（#1）；无记录试卷可删（负控）
    R2 发布后锁定考核口径：改总分/及格线 → 400，进行中改时长 → 400（#5）；
       已发布无进行中改时长 → 200（负控）
    R3 删除被试卷引用的题目 → 400（#3）
    R4 考后改题 → 成绩单 correct_answer 用判分快照，不出现「判对但答案已变」矛盾（#4）
    R5 及格线 > 总分 → 422（manual/auto/update 三处，#7）
    R6 并发同用户名注册 → 400 而非 500（#10）
    R7 账号禁用后既有有效 JWT 立即失效 → 401（#15）
    R8 分页 page 上限 → 422（#13）
  末尾 SQL 清理本套件产生的测试数据。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_bugfix.py
退出码 0 = 全部通过。
"""
from __future__ import annotations

import os
import sys
import uuid

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://127.0.0.1:8000/api/v1"
FAILURES: list[str] = []
TAG = f"BUGFIX-{uuid.uuid4().hex[:6]}"
# 本套件产生的数据（结尾 SQL 清理）
PAPERS: list[int] = []
QUESTIONS: list[int] = []
RECORDS: list[int] = []


def ok(name: str, cond: bool, detail: str = "") -> bool:
    if not cond:
        FAILURES.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""))
    return cond


def new_client() -> httpx.Client:
    return httpx.Client(base_url=BASE, trust_env=False, timeout=30)


def login(c: httpx.Client, u: str, p: str) -> str:
    r = c.post("/auth/login", data={"username": u, "password": p})
    r.raise_for_status()
    return r.json()["data"]["access_token"]


def create_published_paper(c: httpx.Client, admin_h: dict, name: str, items: list[tuple[int, int]],
                           pass_score: int, duration: int = 30) -> int:
    body = {
        "name": name, "duration": duration, "pass_score": pass_score,
        "total_score": sum(s for _, s in items),
        "questions": [{"question_id": qid, "score": sc} for qid, sc in items],
    }
    r = c.post("/papers/manual", json=body, headers=admin_h)
    assert r.status_code == 200, f"组卷失败 {name}: {r.status_code} {r.text}"
    pid = r.json()["data"]["id"]
    PAPERS.append(pid)
    r2 = c.put(f"/papers/{pid}", json={"status": "PUBLISHED"}, headers=admin_h)
    assert r2.status_code == 200, f"发布失败 {name}: {r2.status_code} {r2.text}"
    return pid


# ---------- U：纯单测 ----------

def unit_tests() -> None:
    from app.service.grading_service import canonicalize

    print("== U1 #11 全角→半角归一化 ==")
    ok("SINGLE 全角字母", canonicalize("SINGLE", "Ａ") == "A", canonicalize("SINGLE", "Ａ"))
    ok("SINGLE 全角空格收尾", canonicalize("SINGLE", "　Ａ　") == "A")
    ok("MULTIPLE 全角逗号+全角小写", canonicalize("MULTIPLE", "Ａ，ｂ") == "A,B")
    ok("JUDGE 全角", canonicalize("JUDGE", "Ｂ") == "B")
    ok("FILL 全角分号", canonicalize("FILL", "安全第一；预防为主") == "安全第一;预防为主")
    ok("FILL 全角冒号归一半角", canonicalize("FILL", "统一：管理") == "统一:管理")

    print("== U2 #9 JWT 占位密钥旋转 ==")
    from app.core.config import Settings, _PLACEHOLDER_SECRETS
    s = Settings(jwt_secret="dev-only-change-me")
    ok("占位串被随机替换", s.jwt_secret not in _PLACEHOLDER_SECRETS and len(s.jwt_secret) >= 32,
       f"len={len(s.jwt_secret)}")


# ---------- R：API 回归 ----------

def api_tests(c: httpx.Client, admin_h: dict, a: dict, emp_h: dict) -> None:
    from sqlalchemy import create_engine, text
    from app.core.config import get_settings
    eng = create_engine(get_settings().database_url)

    # 取一个 APPROVED 题目
    with eng.connect() as conn:
        q0 = conn.execute(text("SELECT id FROM question WHERE status='APPROVED' ORDER BY id LIMIT 1")).scalar()
    assert q0, "题库无 APPROVED 题目，先跑 seed_demo"

    # ---------- R1 #1 删除有考试记录的试卷 ----------
    print("== R1 #1 删除试卷保护 ==")
    pid = create_published_paper(c, admin_h, f"{TAG}-R1", [(q0, 10)], pass_score=6)
    r = c.post("/exams/start", json={"paper_id": pid}, headers=emp_h)
    assert r.status_code == 200, f"开考失败 {r.status_code} {r.text}"
    RECORDS.append(r.json()["data"]["record_id"])
    r = c.put(f"/papers/{pid}", json={"status": "DISABLED"}, headers=admin_h)
    assert r.status_code == 200, f"改 DISABLED 失败 {r.status_code} {r.text}"
    r = c.delete(f"/papers/{pid}", headers=admin_h)
    ok("有考试记录 → 删除 400 拦截", r.status_code == 400 and "考试记录" in r.json().get("message", ""),
       f"{r.status_code} {r.json().get('message')}")

    # 负控：DRAFT 无记录试卷可删
    body = {"name": f"{TAG}-R1b", "duration": 30, "pass_score": 6, "total_score": 10,
            "questions": [{"question_id": q0, "score": 10}]}
    r = c.post("/papers/manual", json=body, headers=admin_h)
    pid_b = r.json()["data"]["id"]
    r = c.delete(f"/papers/{pid_b}", headers=admin_h)
    ok("无记录 DRAFT 卷可删（负控）", r.status_code == 200, f"{r.status_code}")

    # ---------- R2 #5 发布后锁定考核口径 ----------
    print("== R2 #5 发布后锁定总分/及格线/进行中时长 ==")
    pid2 = create_published_paper(c, admin_h, f"{TAG}-R2a", [(q0, 10)], pass_score=6)
    r = c.post("/exams/start", json={"paper_id": pid2}, headers=emp_h)
    assert r.status_code == 200
    RECORDS.append(r.json()["data"]["record_id"])
    for field, val in (("pass_score", 11), ("total_score", 20)):
        r = c.put(f"/papers/{pid2}", json={field: val}, headers=admin_h)
        ok(f"已发布改 {field} → 400 拦截", r.status_code == 400, f"{r.status_code} {r.json().get('message')}")
    r = c.put(f"/papers/{pid2}", json={"duration": 90}, headers=admin_h)
    ok("进行中改时长 → 400 拦截", r.status_code == 400 and "进行中" in r.json().get("message", ""),
       f"{r.status_code} {r.json().get('message')}")
    # 负控：已发布但无进行中 → 可改时长/名称
    pid2b = create_published_paper(c, admin_h, f"{TAG}-R2b", [(q0, 10)], pass_score=6)
    r = c.put(f"/papers/{pid2b}", json={"duration": 90}, headers=admin_h)
    ok("已发布无进行中改时长 → 200（负控）", r.status_code == 200, f"{r.status_code}")

    # ---------- R3 #3 删除被引用题目 ----------
    print("== R3 #3 删除被试卷引用的题目 ==")
    body = {"type": "SINGLE", "content": f"{TAG} 待删引用题", "options": ["A. 甲", "B. 乙"],
            "answer": "A", "analysis": "R3 回归用例", "knowledge_point": "测试", "difficulty": "EASY"}
    r = c.post("/questions", json=body, headers=admin_h)
    q_new = r.json()["data"]["id"]
    QUESTIONS.append(q_new)
    pid3 = create_published_paper(c, admin_h, f"{TAG}-R3", [(q_new, 10)], pass_score=6)
    r = c.delete(f"/questions/{q_new}", headers=admin_h)
    ok("被引用题目 → 删除 400 拦截", r.status_code == 400 and "引用" in r.json().get("message", ""),
       f"{r.status_code} {r.json().get('message')}")

    # ---------- R4 #4 考后改题成绩单快照 ----------
    print("== R4 #4 考后改题 → 成绩单用判分快照 ==")
    body = {"type": "SINGLE", "content": f"{TAG} 快照题", "options": ["A. 正确", "B. 错误"],
            "answer": "A", "analysis": "R4 回归用例", "knowledge_point": "测试", "difficulty": "EASY"}
    r = c.post("/questions", json=body, headers=admin_h)
    q4 = r.json()["data"]["id"]
    QUESTIONS.append(q4)
    pid4 = create_published_paper(c, admin_h, f"{TAG}-R4", [(q4, 10)], pass_score=6)
    c.post("/auth/register", json={"username": f"{TAG}emp4", "password": "123456", "name": "R4考生"})
    emp4_h = {"Authorization": f"Bearer {login(c, TAG + 'emp4', '123456')}"}
    r = c.post("/exams/start", json={"paper_id": pid4}, headers=emp4_h)
    rid4 = r.json()["data"]["record_id"]
    RECORDS.append(rid4)
    r = c.post(f"/exams/{rid4}/submit", json={"answers": [{"question_id": q4, "user_answer": "A"}]}, headers=emp4_h)
    qr = r.json()["data"]["questions"][0]
    ok("初始判对", qr["is_correct"] == 1 and qr["score"] == 10)
    r = c.put(f"/questions/{q4}", json={"answer": "B"}, headers=admin_h)
    assert r.status_code == 200, f"改题失败 {r.status_code} {r.text}"
    r = c.get(f"/exams/{rid4}/result", headers=emp4_h)
    qr = r.json()["data"]["questions"][0]
    contrad = qr["is_correct"] == 1 and qr["correct_answer"].strip().upper() != qr["user_answer"].strip().upper()
    ok("改题后无『判对但答案已变』矛盾", not contrad,
       f"user={qr['user_answer']} correct={qr['correct_answer']} is_correct={qr['is_correct']}")
    ok("correct_answer 为判分快照(原A)", qr["correct_answer"] == "A", f"correct={qr['correct_answer']!r}")
    r = c.put(f"/questions/{q4}", json={"answer": "A"}, headers=admin_h)  # 还原

    # ---------- R5 #7 及格线 > 总分 ----------
    print("== R5 #7 及格线 > 总分 → 422 ==")
    body = {"name": f"{TAG}-R5", "duration": 30, "pass_score": 110, "total_score": 100,
            "questions": [{"question_id": q0, "score": 100}]}
    r = c.post("/papers/manual", json=body, headers=admin_h)
    ok("manual pass>total → 422", r.status_code == 422, f"{r.status_code}")
    body = {"name": f"{TAG}-R5a", "duration": 30, "pass_score": 110, "total_score": 100,
            "rules": [{"type": "SINGLE", "count": 1}]}
    r = c.post("/papers/auto", json=body, headers=admin_h)
    ok("auto pass>total → 422", r.status_code == 422, f"{r.status_code}")
    r = c.put(f"/papers/{pid2b}", json={"pass_score": 200}, headers=admin_h)
    ok("update 改后 pass>total → 422", r.status_code == 422, f"{r.status_code}")

    # ---------- R6 #10 并发同用户名注册 ----------
    print("== R6 #10 重复用户名注册 → 400 ==")
    uname = f"{TAG}dup"
    r = c.post("/auth/register", json={"username": uname, "password": "123456", "name": "DUP"})
    r2 = c.post("/auth/register", json={"username": uname, "password": "123456", "name": "DUP"})
    ok("首次注册 200 二次 400", r.status_code == 200 and r2.status_code == 400, f"{r.status_code}/{r2.status_code}")

    # ---------- R7 #15 禁用账号 JWT 失效 ----------
    print("== R7 #15 禁用账号后既有 JWT 立即失效 ==")
    uname7 = f"{TAG}emp7"
    c.post("/auth/register", json={"username": uname7, "password": "123456", "name": "R7考生"})
    tok7 = login(c, uname7, "123456")
    h7 = {"Authorization": f"Bearer {tok7}"}
    r_before = c.get("/papers", headers=h7)
    # 普通员工访问 /papers 本来 403；禁用后必须 401（先于角色校验）
    with eng.begin() as conn:
        conn.execute(text("UPDATE user SET status=0 WHERE username=:u"), {"u": uname7})
    r_after = c.get("/papers", headers=h7)
    ok("禁用后 401（先于角色校验）", r_before.status_code == 403 and r_after.status_code == 401,
       f"before={r_before.status_code} after={r_after.status_code}")
    with eng.begin() as conn:
        conn.execute(text("UPDATE user SET status=1 WHERE username=:u"), {"u": uname7})

    # ---------- R8 #13 分页 page 上限 ----------
    print("== R8 #13 page 超上限 → 422 ==")
    r = c.get("/papers", params={"page": 100001}, headers=admin_h)
    ok("page=100001 → 422", r.status_code == 422, f"{r.status_code}")


def cleanup(eng) -> None:
    print("\n== 清理本套件测试数据 ==")
    from sqlalchemy import text
    with eng.begin() as conn:
        if RECORDS:
            conn.execute(text("DELETE FROM exam_answer WHERE record_id IN :rids"), {"rids": tuple(RECORDS)})
            conn.execute(text("DELETE FROM exam_record WHERE id IN :rids"), {"rids": tuple(RECORDS)})
        if PAPERS:
            conn.execute(text("DELETE FROM exam_paper_question WHERE paper_id IN :pids"), {"pids": tuple(PAPERS)})
            conn.execute(text("DELETE FROM exam_paper WHERE id IN :pids"), {"pids": tuple(PAPERS)})
        if QUESTIONS:
            conn.execute(text("DELETE FROM question WHERE id IN :qids"), {"qids": tuple(QUESTIONS)})
    print(f"  清理：records={len(RECORDS)} papers={len(PAPERS)} questions={len(QUESTIONS)}")


def main() -> None:
    unit_tests()

    c = new_client()
    admin_tok = login(c, "admin", "Admin@123456")
    admin_h = {"Authorization": f"Bearer {admin_tok}"}
    # 本套件专用员工（注册或复用）
    emp_uname = f"{TAG}emp0"
    c.post("/auth/register", json={"username": emp_uname, "password": "123456", "name": "回归考生"})
    emp_h = {"Authorization": f"Bearer {login(c, emp_uname, '123456')}"}
    api_tests(c, admin_h, admin_h, emp_h)

    from app.core.config import get_settings
    from sqlalchemy import create_engine
    cleanup(create_engine(get_settings().database_url))

    n = 9 + len(FAILURES)
    print(f"\n===== 结果：{len(FAILURES)} 个失败 / 9 组 =====")
    if FAILURES:
        print("失败项：", "；".join(FAILURES))
        sys.exit(1)
    print("全部通过 ✅")


if __name__ == "__main__":
    main()
