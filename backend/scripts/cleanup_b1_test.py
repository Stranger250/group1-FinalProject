# -*- coding: utf-8 -*-
"""清理 B1 验证产生的测试隐患数据（标题含「B1 测试」）。"""
import sys

import pymysql

sys.stdout.reconfigure(encoding="utf-8")

conn = pymysql.connect(host="127.0.0.1", port=3306, user="root", password="123456", database="shudao", charset="utf8mb4")
cur = conn.cursor()
cur.execute("SELECT id FROM hazard WHERE title LIKE %s", ("%B1 测试%",))
ids = [r[0] for r in cur.fetchall()]
print("待清理隐患:", ids)
for hid in ids:
    cur.execute("DELETE FROM hazard_image WHERE hazard_id=%s", (hid,))
    cur.execute("DELETE FROM hazard_log WHERE hazard_id=%s", (hid,))
    cur.execute("DELETE FROM hazard WHERE id=%s", (hid,))
conn.commit()
print("已清理", len(ids), "条")
conn.close()
