# -*- coding: utf-8 -*-
"""调试：探查 WPS 在线预览器的分页 DOM 结构（两个站点的预览器差异）。"""
import sys
import time

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

# 用法: python crawler/debug_wps.py <url> [--dump]
# 例: python crawler/debug_wps.py "https://wps.scspc.gov.cn/weboffice/office/w/715705969735233536?_w_appid=ARYQPPAPLJRZTHTQ&_w_third_appid=ARYQPPAPLJRZTHTQ"

url = sys.argv[1]
dump = "--dump" in sys.argv

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    )
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # 等 scrollHeight 稳定
    last_h = -1
    stable = 0
    deadline = time.time() + 40
    while time.time() < deadline:
        time.sleep(2)
        try:
            scroller = page.query_selector(".is-horizontal-scroll")
            tier = page.query_selector(".uil-monitor-tier")
            if scroller and tier:
                h = scroller.evaluate("el => el.scrollHeight")
                if h == last_h:
                    stable += 1
                else:
                    stable = 0
                last_h = h
                if stable >= 2:
                    break
        except Exception:
            pass

    print(f"scrollHeight 稳定: {last_h}")

    # 滚动采集每步 tier 文本，观察分页标记格式
    seen = {}
    for pos in range(0, int(last_h) + 1, 800):
        try:
            page.eval_on_selector(
                ".is-horizontal-scroll", f"el => {{ el.scrollTop = {pos} }}")
        except Exception:
            break
        time.sleep(0.6)
        try:
            tier = page.eval_on_selector(".uil-monitor-tier", "el => el.innerText") or ""
        except Exception:
            tier = ""
        if tier and tier not in seen.values():
            seen[pos] = tier
    print(f"不同 tier 文本数: {len(seen)}")
    for pos, t in seen.items():
        print(f"\n===== pos={pos} (len={len(t)}) 前120字符 =====")
        print(repr(t[:120]))
        if dump:
            open(f"crawler_output/_wps_tier_{pos}.txt", "w", encoding="utf-8").write(t)

    # 页面顶层结构
    info = page.evaluate(
        "() => { const out=[]; const t=document.querySelector('.uil-monitor-tier');"
        " const p=t&&t.parentElement;"
        " out.push('tier.parent='+(p?p.tagName+'.'+String(p.className).slice(0,60):'None'));"
        " if(p){ out.push('children='+p.children.length);"
        "  for(let i=0;i<Math.min(p.children.length,10);i++){"
        "   const c=p.children[i];"
        "   out.push(' child['+i+'] '+c.tagName+'.'+String(c.className).slice(0,50)"
        "    +' len='+(c.innerText||'').length);}}"
        " const all=document.querySelectorAll('.uil-monitor-tier');"
        " out.push('tier.count='+all.length);"
        " return out.join('\\n'); }"
    )
    print("\n=== 结构 ===")
    print(info)
    browser.close()
