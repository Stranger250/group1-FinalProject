# -*- coding: utf-8 -*-
"""
蜀道安全助手 · 规章爬虫入口

用法（在 shudao 目录下运行）：
    # 探测模式：只打印接口/页面结构，不落盘（先跑这个确认字段/选择器）
    python crawler/main.py --probe --source flk --keyword 中华人民共和国安全生产法

    # 单条抓取
    python crawler/main.py --source flk --keyword 中华人民共和国安全生产法

    # 按清单批量抓取（断点续爬）
    python crawler/main.py --targets crawler/targets.json

    # 强制覆盖已存在的
    python crawler/main.py --source flk --keyword 安全生产法 --force

输出目录：crawler_output/（config.OUTPUT_DIR）
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

import config
from core import storage
from core.http import HttpClient
from sources import SOURCES


def build_parser():
    p = argparse.ArgumentParser(description="爬取安全生产规章 → 结构化JSON")
    p.add_argument("--source", choices=list(SOURCES.keys()),
                   help="数据源: flk(法律库) / moj(行政法规库) / dept(部门规章)")
    p.add_argument("--keyword", help="检索关键词（尽量用法规全称）")
    p.add_argument("--law-id", dest="law_id", help="moj 源专用：法规 LawID")
    p.add_argument("--department", default="应急管理部",
                   help="dept 源专用：部委名（应急管理部/交通运输部）")
    p.add_argument("--file-type", type=int, default=2,
                   help="sichuan 源专用：2=政府规章(默认) 1=地方性法规")
    p.add_argument("--targets", help="批量清单 JSON 文件路径")
    p.add_argument("--probe", action="store_true", help="探测模式：只打印不落盘")
    p.add_argument("--force", action="store_true", help="覆盖已存在的 JSON")
    p.add_argument("--output", default=config.OUTPUT_DIR, help="输出目录")
    return p


def run_one(args, source_name, keyword, extra=None):
    """执行单部规章抓取并落盘（probe 模式只打印）。"""
    cls = SOURCES[source_name]
    if source_name == "sichuan":
        # 四川源自带 playwright，不用 HttpClient
        src = cls()
    else:
        src = cls(http=HttpClient(probe=args.probe))
    print(f"\n▶ [{source_name}] 检索：{keyword}")

    t0 = time.time()
    try:
        data = src.fetch(keyword, **(extra or {}))
    except NotImplementedError as e:
        print(f"  ⚠️ {e}")
        return None
    cost = time.time() - t0

    n_articles = sum(len(c["articles"]) for c in data.get("chapters", []))
    print(f"  📄 {data.get('title')} | 章节 {len(data.get('chapters', []))} "
          f"| 条款 {n_articles} | 耗时 {cost:.1f}s")

    if args.probe:
        print("  ── probe: 结构化结果预览（不落盘） ──")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])
        return None

    path = storage.save_regulation(data, args.output)
    storage.update_index({
        "title": data.get("title"),
        "doc_no": data.get("doc_no"),
        "category": data.get("category"),
        "source": data.get("source"),
        "source_url": data.get("source_url"),
        "publish_date": data.get("publish_date"),
        "effective_date": data.get("effective_date"),
        "status": data.get("status"),
        "articles": n_articles,
        "file": path,
    }, args.output)
    print(f"  ✅ 已保存: {path}")
    return path


def main():
    args = build_parser().parse_args()

    if args.targets:
        targets = storage.load_targets(args.targets)
        # 兼容两种格式：顶层是 list，或 {"targets": [...]} 带说明
        if isinstance(targets, dict):
            targets = targets.get("targets", [])
        for item in targets:
            src = item.get("source", "flk")
            keyword = item.get("keyword") or item.get("title")
            if not keyword:
                print(f"  ⏭ 跳过无关键词的条目: {item}")
                continue
            if not args.force and storage.already_fetched(item.get("title", keyword), args.output):
                print(f"  ⏭ 已存在，跳过: {item.get('title', keyword)}")
                continue
            extra = {}
            if item.get("law_id"):
                extra["law_id"] = item["law_id"]
            if item.get("department"):
                extra["department"] = item["department"]
            if item.get("file_type"):
                extra["file_type"] = item["file_type"]
            try:
                run_one(args, src, keyword, extra)
            except Exception as e:
                print(f"  ❌ 失败: {e}")
    elif args.source and args.keyword:
        extra = {}
        if args.source == "moj" and args.law_id:
            extra["law_id"] = args.law_id
        if args.source == "dept":
            extra["department"] = args.department
        if args.source == "sichuan":
            extra["file_type"] = args.file_type
        run_one(args, args.source, args.keyword, extra)
    else:
        print("用法: 需要 --source + --keyword，或 --targets <file>. 详见 --help")


if __name__ == "__main__":
    main()
