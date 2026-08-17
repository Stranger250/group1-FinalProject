# -*- coding: utf-8 -*-
"""O1 验证：隐患分类树接口 + 上报子类 + 列表子类筛选 + 详情子类展示。

用法: python scripts/test_category_flow.py   （BASE_URL 可覆盖，默认 8002）
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


def main():
    ts = datetime.now().strftime("%H%M%S")
    r = requests.post(f"{BASE}/auth/register", json={"username": f"t_cat_{ts}", "password": "Test@123456", "name": "分类测试"}, timeout=20)
    r = requests.post(f"{BASE}/auth/login", data={"username": f"t_cat_{ts}", "password": "Test@123456"}, timeout=20)
    h = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}

    # 1) 分类树
    tree = requests.get(f"{BASE}/hazard-categories", headers=h, timeout=20)
    ok("分类树 200", tree.status_code == 200, tree.text[:100])
    roots = tree.json()["data"]["items"]
    ok("6 个大类", len(roots) == 6, str(len(roots)))
    ga = next((r for r in roots if r["name"] == "高处作业"), None)
    ok("高处作业含子类", bool(ga and ga["children"]), f"{len(ga['children']) if ga else 0} 子类")
    ok("子类含检查项", bool(ga and ga["children"][0].get("check_items")), str(ga["children"][0] if ga else None))

    # 2) 上报带子类
    c = requests.post(f"{BASE}/hazards", headers=h, json={
        "description": "O1测试：高处临边防护缺失", "level": "MAJOR",
        "type": "高处作业", "subcategory": "临边作业"}, timeout=20)
    ok("上报（含子类）200", c.status_code == 200, c.text[:120])
    hid = c.json()["data"]["id"]
    ok("详情含 subcategory", c.json()["data"].get("subcategory") == "临边作业", str(c.json()["data"].get("subcategory")))

    # 3) 列表按子类筛选
    lst = requests.get(f"{BASE}/hazards", headers=h, params={"type": "高处作业", "subcategory": "临边作业", "page_size": 50}, timeout=20).json()["data"]
    ok("子类筛选命中", all(i["subcategory"] == "临边作业" for i in lst["items"]), f"total={lst['total']}")
    lst2 = requests.get(f"{BASE}/hazards", headers=h, params={"type": "高处作业", "subcategory": "配电箱柜", "page_size": 50}, timeout=20).json()["data"]
    ok("不匹配子类筛空", all(i["subcategory"] != "临边作业" for i in lst2["items"]), f"total={lst2['total']}")

    print(f"\nO1 验证结果: PASS={PASS} FAIL={FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
