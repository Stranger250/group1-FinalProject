"""个人中心（T2）+ 用户管理（T3）端到端测试。

前置：后端已在 8000 端口运行（uvicorn app.main:app --reload，需已加载本次改动），MySQL shudao 库就绪。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_profile_e2e.py

覆盖：
  T1 注册测试用户+登录          T2 /auth/me 含 email/avatar/created_time
  T3 改资料（姓名/手机/邮箱）     T4 邮箱格式 422
  T5 改密码（错旧密 400）        T6 改密码正确→新密登录→改回
  T7 头像上传（jpg/png→avatar）  T8 非 ADMIN 访问用户列表 403
  T9 用户列表含测试用户           T10 禁用→登录 403→再启用
  T11 改角色生效                T12 重置密码→新临时密登录
  T13 管理员禁用自身 400         T14 更新不存在用户 404
"""
from __future__ import annotations

import io
import os
import sys
import time

import httpx
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:8000/api/v1")
FAILURES: list[str] = []

ADMIN_USER = "admin"
ADMIN_PWD = "Admin@123456"


def ok(name: str, cond: bool, detail: str = "") -> bool:
    if not cond:
        FAILURES.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""))
    return cond


def new_client() -> httpx.Client:
    return httpx.Client(base_url=BASE, trust_env=False, timeout=30)


def login(client: httpx.Client, username: str, password: str) -> str:
    r = client.post("/auth/login", data={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["data"]["access_token"]


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def make_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (30, 90, 82)).save(buf, format="PNG")
    return buf.getvalue()


def main() -> None:
    suffix = str(int(time.time()))[-6:]
    uname = f"tester_{suffix}"
    pwd = "test123456"

    client = new_client()

    # T1 注册 + 登录
    r = client.post("/auth/register", json={"username": uname, "password": pwd, "name": "测试用户"})
    ok("T1 注册", r.status_code == 200, f"status={r.status_code}")
    emp_tok = login(client, uname, pwd)
    emp_h = auth(emp_tok)

    # T2 /auth/me 含新增字段
    r = client.get("/auth/me", headers=emp_h)
    me = r.json()["data"]
    ok("T2 /me 含 email/avatar/created_time",
       r.status_code == 200 and "email" in me and "avatar" in me and "created_time" in me,
       f"keys={sorted(me.keys())}")

    # T3 改资料
    r = client.put("/auth/profile", json={"name": "新名字", "phone": "13800138000", "email": "t@example.com"}, headers=emp_h)
    d = r.json().get("data", {})
    ok("T3 改资料生效", r.status_code == 200 and d.get("name") == "新名字" and d.get("email") == "t@example.com",
       f"name={d.get('name')} email={d.get('email')}")

    # T4 邮箱格式 422
    r = client.put("/auth/profile", json={"name": "新名字", "email": "bad-email"}, headers=emp_h)
    ok("T4 邮箱格式 422", r.status_code == 422, f"status={r.status_code}")

    # T5 错旧密 400
    r = client.put("/auth/password", json={"old_password": "wrong", "new_password": "newpass888"}, headers=emp_h)
    ok("T5 错原密码 400", r.status_code == 400, f"status={r.status_code}")

    # T6 改密码→新密登录→改回
    r = client.put("/auth/password", json={"old_password": pwd, "new_password": "newpass888"}, headers=emp_h)
    if ok("T6a 改密码成功", r.status_code == 200, f"status={r.status_code}"):
        emp_tok = login(client, uname, "newpass888")
        emp_h = auth(emp_tok)
        client.put("/auth/password", json={"old_password": "newpass888", "new_password": pwd}, headers=emp_h)

    # T7 头像上传
    r = client.post("/auth/avatar", files={"file": ("a.png", make_png(), "image/png")}, headers=emp_h)
    av = r.json().get("data", {})
    ok("T7 头像上传并落库", r.status_code == 200 and (av.get("avatar") or "").startswith("/uploads/"),
       f"avatar={av.get('avatar')}")

    # T8 员工访问用户列表 403
    r = client.get("/users", headers=emp_h)
    ok("T8 非 ADMIN 403", r.status_code == 403, f"status={r.status_code}")

    # ---- 管理端 ----
    admin_tok = login(client, ADMIN_USER, ADMIN_PWD)
    admin_h = auth(admin_tok)
    me_r = client.get("/auth/me", headers=admin_h)
    admin_id = me_r.json()["data"]["id"]

    # T9 列表含测试用户
    r = client.get("/users", params={"keyword": uname}, headers=admin_h)
    items = r.json()["data"]["items"]
    target = next((u for u in items if u["username"] == uname), None)
    ok("T9 列表含测试用户", r.status_code == 200 and target is not None,
       f"total={r.json()['data']['total']}")

    # T10 禁用→登录 403→再启用
    r = client.put(f"/users/{target['id']}", json={"status": 0}, headers=admin_h)
    ok("T10a 禁用", r.status_code == 200 and r.json()["data"]["status"] == 0, f"status={r.status_code}")
    r = client.post("/auth/login", data={"username": uname, "password": pwd})
    ok("T10b 禁用后登录 403", r.status_code == 403, f"status={r.status_code}")
    r = client.put(f"/users/{target['id']}", json={"status": 1}, headers=admin_h)
    ok("T10c 重新启用", r.status_code == 200 and r.json()["data"]["status"] == 1, f"status={r.status_code}")

    # T11 改角色 SAFETY→验证 →改回 EMPLOYEE
    r = client.put(f"/users/{target['id']}", json={"role_id": 2}, headers=admin_h)
    ok("T11 改角色为安全员", r.status_code == 200 and r.json()["data"]["role_id"] == 2, f"status={r.status_code}")
    client.put(f"/users/{target['id']}", json={"role_id": 1}, headers=admin_h)

    # T12 重置密码→临时密登录
    r = client.post(f"/users/{target['id']}/reset-password", headers=admin_h)
    temp_pwd = r.json().get("data", {}).get("new_password")
    ok("T12a 重置密码返回临时密", r.status_code == 200 and bool(temp_pwd), f"status={r.status_code}")
    r = client.post("/auth/login", data={"username": uname, "password": temp_pwd})
    ok("T12b 临时密码可登录", r.status_code == 200, f"status={r.status_code}")

    # T13 管理员禁用自身 400
    r = client.put(f"/users/{admin_id}", json={"status": 0}, headers=admin_h)
    msg = ""
    try:
        msg = r.json().get("message", "")
    except ValueError:
        pass
    ok("T13 禁用自身 400", r.status_code == 400, f"status={r.status_code} msg={msg}")

    # T14 更新不存在用户 404
    r = client.put("/users/99999999", json={"status": 1}, headers=admin_h)
    ok("T14 不存在用户 404", r.status_code == 404, f"status={r.status_code}")

    print(f"\n结果：{'全部通过 ✅' if not FAILURES else '失败 ' + str(len(FAILURES)) + ' 项：' + str(FAILURES)}")


if __name__ == "__main__":
    main()
