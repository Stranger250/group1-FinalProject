# -*- coding: utf-8 -*-
"""O8 考试工坊验证：用户添加题目(待审核) → 管理员审核 → 组卷 → 发布考试给指定用户 → 被分享者作答/收藏 → 撤销 → Word 导出。

用法: python scripts/test_workshop_flow.py   （BASE_URL 可覆盖，默认 8002）
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


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f" | {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f" | {detail}" if detail else ""))


def login(username, password):
    r = requests.post(f"{BASE}/auth/login", data={"username": username, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {username} failed: {r.text[:150]}"
    d = r.json()["data"]
    uid = d.get("user", {}).get("id") if isinstance(d.get("user"), dict) else None
    return {"Authorization": "Bearer " + d["access_token"]}, uid


def main():
    ts = datetime.now().strftime("%H%M%S")
    u1 = f"t_wk1_{ts}"
    u2 = f"t_wk2_{ts}"
    for un, nm in ((u1, "组卷用户"), (u2, "被分享用户")):
        requests.post(f"{BASE}/auth/register", json={"username": un, "password": "Test@123456", "name": nm}, timeout=20)
    h1, uid1 = login(u1, "Test@123456")
    h2, uid2 = login(u2, "Test@123456")
    ha, _ = login("admin", "Admin@123456")

    # 1) 用户添加题目 → PENDING
    c = requests.post(f"{BASE}/questions", headers=h1, json={
        "type": "SINGLE", "content": f"O8测试题{ts}：安全生产方针是什么？",
        "options": ["A 安全第一，预防为主，综合治理", "B 效益优先", "C 速度优先", "D 成本优先"],
        "answer": "A", "analysis": "安全生产法规定", "difficulty": "EASY", "knowledge_point": "安全生产法"}, timeout=20)
    ok("用户添加题目 200", c.status_code == 200, c.text[:120])
    qid = c.json()["data"]["id"]
    ok("用户提交题目为 PENDING", c.json()["data"]["status"] == "PENDING", str(c.json()["data"]["status"]))

    # 2) 用户查询题库：看不到 PENDING 题
    lst = requests.get(f"{BASE}/questions", headers=h2, params={"page_size": 50}, timeout=20).json()["data"]
    ok("普通用户题库不见 PENDING 题", all(i["status"] == "APPROVED" for i in lst["items"]), f"total={lst['total']}")

    # 3) 管理员审核通过 → APPROVED
    rv = requests.post(f"{BASE}/questions/{qid}/review", headers=ha, json={"action": "APPROVE"}, timeout=20)
    ok("管理员审核通过 200", rv.status_code == 200, rv.text[:120])
    dq = requests.get(f"{BASE}/questions/{qid}", headers=h2, timeout=20)
    ok("审核后用户可见 APPROVED", dq.status_code == 200 and dq.json()["data"]["status"] == "APPROVED", "")

    # 4) 用户组卷
    cp = requests.post(f"{BASE}/my-papers", headers=h1, json={
        "name": f"O8组卷{ts}", "duration": 30, "pass_score": 60, "total_score": 100,
        "questions": [{"question_id": qid, "score": 100}]}, timeout=20)
    ok("用户组卷 200", cp.status_code == 200, cp.text[:120])
    pid = cp.json()["data"]["id"]

    # 5) 发布考试给用户2
    pub = requests.post(f"{BASE}/my-papers/{pid}/publish", headers=h1, json={"target_user_ids": [uid2]}, timeout=20)
    ok("发布考试 200", pub.status_code == 200, pub.text[:150])
    shares = requests.get(f"{BASE}/my-papers/{pid}/shares", headers=h1, timeout=20).json()["data"]["items"]
    ok("发布列表含用户2", any(s["target_user_id"] == uid2 for s in shares), str(shares))

    # 6) 用户2 可见分享给我的 + 概要脱敏
    sp = requests.get(f"{BASE}/shared-papers", headers=h2, timeout=20).json()["data"]
    ok("被分享者可见试卷", any(i["id"] == pid for i in sp["items"]), f"total={sp['total']}")
    sd = requests.get(f"{BASE}/shared-papers/{pid}", headers=h2, timeout=20).json()["data"]
    q0 = sd["questions"][0]
    ok("概要答案脱敏", "answer" not in q0, str(list(q0.keys())))

    # 7) 被分享者作答（复用 /exams/start）
    st = requests.post(f"{BASE}/exams/start", headers=h2, json={"paper_id": pid}, timeout=20)
    ok("被分享者开始作答 200", st.status_code == 200, st.text[:150])
    rec_id = st.json()["data"]["record_id"]

    # 8) 收藏副本
    cp2 = requests.post(f"{BASE}/shared-papers/{pid}/copy", headers=h2, timeout=20)
    ok("收藏副本 200", cp2.status_code == 200, cp2.text[:150])
    copy_id = cp2.json()["data"]["id"]
    ok("副本 source_paper_id 标记", cp2.json()["data"].get("source_paper_id") == pid, str(cp2.json()["data"].get("source_paper_id")))
    mine = requests.get(f"{BASE}/my-papers", headers=h2, timeout=20).json()["data"]
    ok("副本出现在我的试卷", any(i["id"] == copy_id for i in mine["items"]), "")

    # 9) 撤销发布 → 用户2 不可再见/作答
    uid2 = uid2
    rv2 = requests.delete(f"{BASE}/my-papers/{pid}/shares/{uid2}", headers=h1, timeout=20)
    ok("撤销发布 200", rv2.status_code == 200, rv2.text[:120])
    sp2 = requests.get(f"{BASE}/shared-papers", headers=h2, timeout=20).json()["data"]
    ok("撤销后不可见", all(i["id"] != pid for i in sp2["items"]), "")
    sd2 = requests.get(f"{BASE}/shared-papers/{pid}", headers=h2, timeout=20)
    ok("撤销后详情 404", sd2.status_code == 404, f"status={sd2.status_code}")
    # 已收藏副本仍可作答（继续进行中的考试）
    resume = requests.get(f"{BASE}/exams/{rec_id}", headers=h2, timeout=20)
    ok("已收藏/已开考不受撤销影响", resume.status_code == 200, f"status={resume.status_code}")

    # 10) Word 导出
    for ans, label in ((0, "仅题目版"), (1, "含答案版")):
        w = requests.get(f"{BASE}/my-papers/{pid}/export-word", headers=h1, params={"answers": ans}, timeout=30)
        ok(f"导出 Word（{label}）", w.status_code == 200 and w.headers.get("content-type", "").startswith("application/vnd"),
           f"status={w.status_code} len={len(w.content)}")

    # 11) 用户搜索（发布考试选择目标用户）
    su = requests.get(f"{BASE}/users/search", headers=h1, params={"keyword": "被分享"}, timeout=20).json()["data"]
    ok("用户搜索按昵称命中", any(i["id"] == uid2 for i in su["items"]), str(su["items"])[:80])

    print(f"\nO8 验证结果: PASS={PASS} FAIL={FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
