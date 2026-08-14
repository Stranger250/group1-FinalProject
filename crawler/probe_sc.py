# -*- coding: utf-8 -*-
"""
四川法规规章数据库探测脚本（playwright）

用途：打开四川库分类页，等 JS 加载后抓取列表接口的真实参数/响应，
以及详情页全文结构。--probe 模式下只打印不落盘。

用法（等 chromium 装好后运行）：
    python crawler/probe_sc.py --type gov --keyword 安全生产
"""
import argparse
import json
import sys
import time

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    p = argparse.ArgumentParser(description="探测四川法规规章数据库")
    p.add_argument("--type", default="gov", help="分类: gov=政府规章 / local=地方性法规")
    p.add_argument("--keyword", default="", help="搜索关键词")
    p.add_argument("--page", default=1, type=int, help="页码")
    args = p.parse_args()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1400, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"),
        )

        # 收集所有 XHR/fetch 响应
        captured = []
        page.on("response", lambda resp: captured.append(resp))

        url = f"https://rhpt.scspc.gov.cn/flfgkgzd/{args.type}"
        print(f"打开: {url}")
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(3)

        # 打印拦截到的 API 响应
        print("\n=== 拦截到的 API 响应 ===")
        for resp in captured:
            u = resp.url
            if "publicPlatform" in u or "api" in u or "search" in u or "list" in u:
                try:
                    body = resp.text()[:600]
                except Exception:
                    body = "(不可读)"
                print(f"\n--- {resp.status} {u[:90]} ---")
                print(body.replace("\n", " ")[:600])
            else:
                print(f"  (其他) {resp.status} {u[:70]}")

        # 尝试在页面搜索框输入关键词
        if args.keyword:
            try:
                # 常见输入框选择器
                box = (page.locator("input[placeholder*='关键词'], input[placeholder*='标题'], "
                                    "input[placeholder*='检索'], input[placeholder*='查询']").first)
                if box.count() > 0:
                    box.fill(args.keyword)
                    page.keyboard.press("Enter")
                    time.sleep(3)
                    print(f"\n=== 搜索「{args.keyword}」后 ===")
                    print("页面文本片段:", page.locator("body").inner_text()[:600].replace("\n", " "))
            except Exception as e:
                print(f"搜索尝试失败: {e}")

        browser.close()


if __name__ == "__main__":
    main()
