"""验证 MySQL root 密码并写回 backend/.env（自动 URL 编码）。

解决：DATABASE_URL 里的密码若含 @ / : # 等特殊字符，手写会出错
（解析截断 → 1045 Access denied）。本工具输入真实密码 → 验证连接 →
URL 编码后写回 .env，全程不回显、不打印密码。

运行：cd shudao/backend && python scripts/set_db_password.py
成功后即可：python scripts/init_db.py
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path
from urllib.parse import quote

import pymysql
from sqlalchemy.engine import make_url

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
HOST, PORT, DB = "127.0.0.1", 3306, "shudao"


def main() -> None:
    if not ENV_PATH.exists():
        sys.exit(f"未找到 .env：{ENV_PATH}")

    pw = getpass.getpass("请输入 MySQL root 密码（输入不会显示）: ")
    if not pw:
        sys.exit("密码为空，退出（如 root 确无密码，请先在 MySQL 里设置一个）。")

    # 1) 用原始密码验证连接
    try:
        conn = pymysql.connect(host=HOST, port=PORT, user="root", password=pw, connect_timeout=5)
        conn.close()
    except Exception as e:
        print(f"✗ 连接失败：{type(e).__name__}：{e}")
        print("  → 该密码不是本机 MySQL root 的真实密码，请核对；")
        print("  → 若确认无误仍失败，需重置 root 密码（见文档/联系我）。")
        sys.exit(1)

    # 2) URL 编码后写回 .env
    enc = quote(pw, safe="")
    url = f"mysql+pymysql://root:{enc}@{HOST}:{PORT}/{DB}?charset=utf8mb4"

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    found, out = False, []
    for line in lines:
        if line.startswith("DATABASE_URL"):
            out.append(f"DATABASE_URL={url}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"DATABASE_URL={url}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")

    # 3) 用写回后的 URL 再验证一遍（确认编码无副作用）
    u = make_url(url)
    conn = pymysql.connect(host=u.host, port=u.port, user=u.username, password=u.password)
    conn.close()
    print(f"✓ 密码验证通过，已写入 .env（URL 编码，{len(pw)} 位）")
    print("  下一步：python scripts/init_db.py")


if __name__ == "__main__":
    main()
