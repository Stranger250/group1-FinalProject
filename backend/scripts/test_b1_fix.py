"""M0 B1 验证：图片可见性 + risk_report 保留/不保留落库 + /uploads 静态访问。

用法: python scripts/test_b1_fix.py   (默认 http://127.0.0.1:8002/api/v1)
环境: BASE_URL 可覆盖
"""
import io
import json
import os
import sys
import time

import httpx
import requests

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8002/api/v1")
ROOT = os.environ.get("ROOT_URL", "http://127.0.0.1:8002")

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name} {extra}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


def login(username, password):
    r = requests.post(f"{BASE}/auth/login", data={"username": username, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {username} failed: {r.status_code} {r.text[:200]}"
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def main():
    h = login("admin", "Admin@123456")

    # 1) 上传一张测试图（生成 1x1 PNG）
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da63fcffff3f030005fe02fea72e2f4d0000000049454e44ae426082"
    )
    up = requests.post(
        f"{BASE}/hazards/upload",
        headers=h,
        files={"file": ("b1_test.png", io.BytesIO(png), "image/png")},
        timeout=30,
    )
    check("上传图片 200", up.status_code == 200, f"status={up.status_code} body={up.text[:150]}")
    if up.status_code != 200:
        return
    url = up.json()["data"]["url"]
    check("上传返回 /uploads/ 路径", url.startswith("/uploads/"), url)

    # 2) 静态访问图片（模拟重启后可见性：直接 GET 容器根 URL）
    st = requests.get(f"{ROOT}{url}", timeout=20)
    check("静态访问图片 200", st.status_code == 200, f"status={st.status_code}")

    # 3) 上报（保留 AI 识别：kept=true）
    rr = {
        "kept": True,
        "type_suggest": "用电安全",
        "level_suggest": "MAJOR",
        "description": "配电箱未接地",
        "confidence": 0.92,
        "detections": [{"label": "配电箱", "confidence": 0.9, "bbox": [0.1, 0.1, 0.5, 0.5]}],
        "annotated_url": url,
    }
    c = requests.post(
        f"{BASE}/hazards",
        headers=h,
        json={"description": "B1 测试：配电箱未接地，存在触电风险", "level": "MAJOR", "type": "用电安全", "images": [url], "risk_report": rr},
        timeout=20,
    )
    check("上报（kept=true）200", c.status_code == 200, f"status={c.status_code} body={c.text[:150]}")
    if c.status_code != 200:
        return
    hid1 = c.json()["data"]["id"]

    # 4) 上报（不保留识别：risk_report=null）
    c2 = requests.post(
        f"{BASE}/hazards",
        headers=h,
        json={"description": "B1 测试：不保留识别", "level": "GENERAL", "images": [url], "risk_report": None},
        timeout=20,
    )
    check("上报（不保留）200", c2.status_code == 200, f"status={c2.status_code}")
    hid2 = c2.json()["data"]["id"]

    # 5) 详情1：risk_report 含 kept=true 与 detections
    d1 = requests.get(f"{BASE}/hazards/{hid1}", headers=h, timeout=20).json()["data"]
    rr1 = d1.get("risk_report") or {}
    check("详情1 risk_report.kept=true", rr1.get("kept") is True, json.dumps(rr1, ensure_ascii=False)[:120])
    check("详情1 detections 保留", bool(rr1.get("detections")), "")
    check("详情1 图片列表含上传图", any(i["image_url"] == url for i in d1.get("images", [])), "")

    # 6) 详情2：risk_report 为 null（仅原图）
    d2 = requests.get(f"{BASE}/hazards/{hid2}", headers=h, timeout=20).json()["data"]
    check("详情2 risk_report 为 null", d2.get("risk_report") is None, "")

    # 7) 详情接口输出结构含 risk_report（前端 kept 渲染依据）
    dk = sorted(d1.keys())
    check("详情输出含 risk_report 字段", "risk_report" in dk, "")

    print(f"\nB1 验证结果: PASS={PASS} FAIL={FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
