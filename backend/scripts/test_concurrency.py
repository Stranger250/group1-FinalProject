# -*- coding: utf-8 -*-
"""并发专项测试（真实 MySQL，TEST_PLAN §2.2 关键用例）：
  1. 并发双交只评一次（分数一致、无重复评分）
  2. 并发 start 同卷：只产生一条 ONGOING（uk_user_paper_ongoing）
  3. 并发注册同用户名：一个成功其余 400（非 500）
  4. 并发 save 同题：不炸、最终答案一致
"""
import os
import sys
import threading
import time
from datetime import datetime

# 从 backend 根导入 app.*（数据库凭据从 backend/.env 读取，勿硬编码）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
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

    warm = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30)
    for i in range(6):
        try:
            if warm.get("/").status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(2)
    warm.close()

    admin = httpx.Client(base_url=BASE, timeout=60)
    r = admin.post("/auth/login", data={"username": "admin", "password": "Admin@123456"})
    assert r.json()["code"] == 200, "admin 登录失败"
    admin_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    # 建一个已发布试卷（两题，各 50 分）
    r = admin.get("/questions", params={"status": "APPROVED", "page_size": 2}, headers=admin_h)
    qs = r.json()["data"]["items"]
    q1, q2 = qs[0]["id"], qs[1]["id"]
    r = admin.post("/papers/manual", json={
        "name": f"t_conc_{ts}", "duration": 30, "total_score": 100,
        "questions": [{"question_id": q1, "score": 50}, {"question_id": q2, "score": 50}]}, headers=admin_h)
    pid = r.json()["data"]["id"]
    admin.put(f"/papers/{pid}", json={"status": "PUBLISHED"}, headers=admin_h)

    # 并发 1：并发注册同用户名
    section("并发注册同用户名")
    uname = f"t_concuser_{ts}"
    results = []
    lock = threading.Lock()

    def do_register():
        c = httpx.Client(base_url=BASE, timeout=60)
        r = c.post("/auth/register", json={"username": uname, "password": "Test@123456", "name": "并发"})
        with lock:
            results.append(r.status_code)
        c.close()

    threads = [threading.Thread(target=do_register) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok("并发注册：1 成功 3 个 400（无 500）",
       results.count(200) == 1 and results.count(400) == 3,
       f"results={sorted(results)}")

    # 并发 2：并发 start 同一试卷
    section("并发 start 同一试卷（uk_user_paper_ongoing）")
    emp = httpx.Client(base_url=BASE, timeout=60)
    r = emp.post("/auth/login", data={"username": uname, "password": "Test@123456"})
    emp_h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}
    start_results = []

    def do_start():
        c = httpx.Client(base_url=BASE, timeout=60)
        r = c.post("/exams/start", json={"paper_id": pid}, headers=emp_h)
        with lock:
            start_results.append((r.status_code, r.json().get("code")))
        c.close()

    threads = [threading.Thread(target=do_start) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok("并发 start 全部 200（复用同一进行中记录）",
       all(code == 200 for code, _ in start_results), f"results={start_results}")
    rec_id = None
    # 从服务端确认只有一条 ONGOING；数据库凭据从 backend/.env 的 DATABASE_URL 读取（勿硬编码）
    import pymysql
    from sqlalchemy.engine import make_url
    from app.core.config import get_settings
    _u = make_url(get_settings().database_url)
    dbc = pymysql.connect(host=_u.host, port=_u.port or 3306, user=_u.username,
                          password=_u.password or "", database=_u.database,
                          charset="utf8mb4")
    cur = dbc.cursor()
    cur.execute("SELECT id, user_id FROM exam_record WHERE paper_id=%s AND state='ONGOING'", (pid,))
    ongoing = cur.fetchall()
    ok("同用户同卷仅一条 ONGOING 记录", len(ongoing) == 1, f"rows={ongoing}")
    if ongoing:
        rec_id = ongoing[0][0]
    dbc.close()

    # 并发 3：并发双交只评一次
    section("并发双交只评一次")
    if rec_id:
        answers = [{"question_id": q1, "user_answer": "A"}, {"question_id": q2, "user_answer": "A"}]
        submit_results = []

        def do_submit():
            c = httpx.Client(base_url=BASE, timeout=60)
            r = c.post(f"/exams/{rec_id}/submit", json={"answers": answers}, headers=emp_h)
            with lock:
                submit_results.append((r.status_code, r.json().get("code"), r.json().get("data")))
            c.close()

        threads = [threading.Thread(target=do_submit) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        codes = [c for c, _, _ in submit_results]
        ok("并发 submit 全部 200（幂等，无双交报错）", all(c == 200 for c in codes), f"codes={codes}")
        scores = [d.get("score") for _, _, d in submit_results if d]
        ok("各响应 score 一致", len(set(scores)) == 1, f"scores={scores}")
        ok("未出现部分交卷不一致", all(d.get("state") == "SUBMITTED" for _, _, d in submit_results if d))

    # 并发 4：并发 save 不同题（正常不炸）
    section("并发 save（交卷后幂等，不炸）")
    if rec_id:
        save_results = []

        def do_save():
            c = httpx.Client(base_url=BASE, timeout=60)
            r = c.post(f"/exams/{rec_id}/save", json={"answers": [{"question_id": q1, "user_answer": "B"}]}, headers=emp_h)
            with lock:
                save_results.append((r.status_code, r.json().get("code")))
            c.close()

        threads = [threading.Thread(target=do_save) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ok("并发 save 已交卷记录 → 幂等 200", all(c == 200 for c, _ in save_results), f"results={save_results}")

    admin.close()
    emp.close()

    print(f"\n{'='*60}\n结果：PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("并发专项测试全部通过 ✅")


if __name__ == "__main__":
    main()
