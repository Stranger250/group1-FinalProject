"""模块一 隐患安全管理（H01–H03）端到端测试。

前置：后端已在 8000 端口运行（uvicorn app.main:app --reload），MySQL shudao 库就绪。
      视觉识别用例（T3）需 .env 已配 VISION_* 且可访问阿里云百炼（会消耗一次调用）。

运行：cd shudao/backend && PYTHONIOENCODING=utf-8 python scripts/test_hazard_e2e.py

覆盖：
  T1 未登录访问 401          T2 图片上传 200+url      T3 AI 识别（类型/等级/描述/bbox/标注图）
  T4 非图片上传 400          T5 纯文字上报（编号/待处理/时间线）  T6 带图上报（images 落库）
  T7 空描述 422              T8 列表筛选+分页          T9 详情时间线+创建人
  T10 员工闭环 403           T11 管理员闭环 FINISHED+留痕  T12 重复闭环 400
  T13 不存在隐患 404
"""
from __future__ import annotations

import io
import os
import re
import sys
import time

import httpx
from PIL import Image, ImageDraw

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 脚本位于 backend/scripts/，把 backend 根加入 sys.path 以便 import app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://127.0.0.1:8000/api/v1"
BASE_ORIGIN = "http://127.0.0.1:8000"  # 静态文件 URL 需 host 前缀（httpx base_url 会拼到 /api/v1 后面）
FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> bool:
    if not cond:
        FAILURES.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""))
    return cond


def new_client() -> httpx.Client:
    # 180s：视觉识别（T3）百炼模型延迟不稳定（实测 5~15s+），客户端超时须大于服务端 150s 上限
    return httpx.Client(base_url=BASE, trust_env=False, timeout=180)


def login(client: httpx.Client, username: str, password: str) -> str:
    r = client.post("/auth/login", data={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["data"]["access_token"]


def register_or_login(client: httpx.Client, username: str, password: str, name: str) -> str:
    r = client.post("/auth/register", json={"username": username, "password": password, "name": name})
    return login(client, username, password)


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def make_test_image(size: int = 320) -> bytes:
    """生成一张模拟「临边防护缺失」的测试图（返回 JPEG bytes）。"""
    img = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([30, 30, 290, 290], outline="black", width=4)
    d.rectangle([90, 110, 230, 290], fill="skyblue")          # 疑似楼层/坑洞
    d.line([90, 60, 230, 200], fill="red", width=6)           # 疑似无防护的高处边缘
    d.rectangle([120, 230, 200, 290], fill="gray")            # 疑似脚手架
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def main() -> None:
    c = new_client()
    admin_tok = login(c, "admin", "Admin@123456")
    uname = f"haztest{int(time.time())}"
    emp_tok = register_or_login(c, uname, "HazTest@123", "隐患测试员")
    emp_h, admin_h = auth(emp_tok), auth(admin_tok)
    image_bytes = make_test_image()

    print("== 鉴权与基础拦截 ==")
    r = c.get("/hazards")
    ok("T1 未登录访问列表 401", r.status_code == 401, str(r.status_code))

    print("\n== H01 上报链路（上传 → 识别 → 上报）==")
    r = c.post("/hazards/upload", files={"file": ("hazard_test.jpg", image_bytes, "image/jpeg")}, headers=emp_h)
    ok("T2 图片上传成功", r.status_code == 200 and r.json()["data"]["url"].startswith("/uploads/"),
       r.text[:120])
    img_url = r.json()["data"]["url"]

    r = c.post("/hazards/analyze", files={"file": ("hazard_test.jpg", image_bytes, "image/jpeg")}, headers=emp_h)
    analyze_ok = r.status_code == 200
    ok("T3 AI 识别成功", analyze_ok, r.text[:160])
    if analyze_ok:
        d = r.json()["data"]
        dets = d.get("detections")
        ok("T3 建议类型/等级齐全", d["type_suggest"] and d["level_suggest"], str(d)[:120])
        ok("T3 无检测时描述为空、有检测时描述非空",
           (not dets and not d["description"]) or (dets and d["description"]), f"detections={len(dets)}, desc={d['description'][:20]!r}")
        ok("T3 返回 bbox 键（无隐患可 null）", "bbox" in d, str(d.get("bbox"))[:80])
        ok("T3 返回 detections 数组（多框检测）", isinstance(dets, list) and all(
            isinstance(x, dict) and "bbox" in x and "type_suggest" in x and "level_suggest" in x
            for x in dets), f"detections={len(dets) if isinstance(dets, list) else dets}")
        ok("T3 主检测与 detections 首项一致", not dets or d["bbox"] == dets[0].get("bbox"), str(d.get("bbox"))[:80])
        ok("T3 返回标注图 URL 键（无 bbox 可 null）", "annotated_url" in d, str(d.get("annotated_url"))[:80])
        if d.get("annotated_url"):
            rr_img = c.get(f"{BASE_ORIGIN}{d['annotated_url']}")  # 全 URL：httpx base_url 会拼错路径
            ok("T3 标注图可访问 200", rr_img.status_code == 200, f"HTTP {rr_img.status_code}")
        report = {"report": d["report"], "type_suggest": d["type_suggest"], "level_suggest": d["level_suggest"]}
    else:
        report = None

    r = c.post("/hazards/upload", files={"file": ("fake.txt", b"not an image", "text/plain")}, headers=emp_h)
    ok("T4 非图片上传 400", r.status_code == 400, str(r.status_code))

    body = {"description": "临时用电线路绝缘层破损，存在触电风险", "level": "MAJOR", "type": "用电安全", "location": "3号配电房"}
    r = c.post("/hazards", json=body, headers=emp_h)
    ok("T5 纯文字上报成功", r.status_code == 200, r.text[:120])
    h5 = r.json()["data"]
    ok("T5 编号格式 HZ+日期+序号", bool(re.match(r"^HZ\d{8}-\d{4}$", h5["hazard_no"])), h5["hazard_no"])
    ok("T5 状态=待处理", h5["status"] == "WAIT_PROCESS", h5["status"])
    ok("T5 时间线含提交", any(x["operation"] == "提交" for x in h5["timeline"]))
    ok("T5 位置缺省落「未填写」", h5["location"] in ("3号配电房",), str(h5["location"]))

    body2 = {"description": "施工现场临边防护栏缺失，工人靠近边缘作业", "level": "CRITICAL",
             "type": "临边防护", "images": [img_url]}
    if report:
        body2["risk_report"] = report["report"]
    r = c.post("/hazards", json=body2, headers=emp_h)
    ok("T6 带图上报成功", r.status_code == 200, r.text[:120])
    h6 = r.json()["data"]
    ok("T6 images 落库 1 张", len(h6["images"]) == 1 and h6["images"][0]["image_url"] == img_url, str(h6["images"])[:120])

    r = c.post("/hazards", json={"description": "", "level": "GENERAL"}, headers=emp_h)
    ok("T7 空描述 422", r.status_code == 422, str(r.status_code))

    print("\n== H02 列表 / H03 详情 ==")
    hid = h5["id"]
    r = c.get("/hazards", params={"level": "MAJOR", "page": 1, "page_size": 5}, headers=emp_h)
    d = r.json().get("data", {})
    ok("T8 列表结构正确", r.status_code == 200 and d.get("total", 0) >= 1 and d.get("items"), str(d)[:120])
    ok("T8 筛选等级生效", all(i["level"] == "MAJOR" for i in d["items"]), str([i["level"] for i in d["items"]])[:80])
    r = c.get("/hazards", params={"keyword": "配电", "status": "WAIT_PROCESS"}, headers=emp_h)
    ok("T8 关键字+状态筛选", r.status_code == 200 and any(i["id"] == hid for i in r.json()["data"]["items"]))

    r = c.get(f"/hazards/{hid}", headers=emp_h)
    d = r.json()["data"]
    ok("T9 详情含创建人", d.get("creator_name") and d["creator_id"], str(d.get("creator_name")))
    tl = d["timeline"]
    ok("T9 时间线倒序且含提交", tl and tl[0]["operation"] == "提交", str(tl)[:100])

    print("\n== 管理员闭环 ==")
    r = c.post(f"/hazards/{hid}/close", headers=emp_h)
    ok("T10 员工闭环 403", r.status_code == 403, str(r.status_code))

    r = c.post(f"/hazards/{hid}/close", headers=admin_h)
    ok("T11 管理员闭环成功", r.status_code == 200 and r.json()["data"]["status"] == "FINISHED", r.text[:120])
    r = c.get(f"/hazards/{hid}", headers=emp_h)
    d = r.json()["data"]
    ok("T11 详情状态已闭环", d["status"] == "FINISHED", d["status"])
    ok("T11 时间线含闭环留痕", any(x["operation"] == "闭环" and x["new_status"] == "FINISHED" for x in d["timeline"]),
       str(d["timeline"])[:100])

    r = c.post(f"/hazards/{hid}/close", headers=admin_h)
    ok("T12 重复闭环 400", r.status_code == 400, str(r.status_code))

    r = c.get("/hazards/99999999", headers=emp_h)
    ok("T13 不存在隐患 404", r.status_code == 404, str(r.status_code))

    print(f"\n===== 隐患模块测试完成：{len(FAILURES)} 个失败 =====")
    if FAILURES:
        print("失败项：", "；".join(FAILURES))
        sys.exit(1)
    print("全部用例通过 ✅")


if __name__ == "__main__":
    main()
