# -*- coding: utf-8 -*-
"""
JSON 落盘 + 元数据索引 + 断点续爬支持。
"""
import json
import os
import re


def safe_filename(title):
    """把规章标题转成合法文件名。"""
    name = re.sub(r'[\\/:*?"<>|\s]+', '_', title)
    return name.strip('_') or 'unnamed'


def save_regulation(data, output_dir):
    """单部规章存为一个 JSON 文件，返回文件路径。"""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{safe_filename(data.get('title', 'unnamed'))}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_index(output_dir):
    """读取 index.json，不存在则返回空列表。"""
    path = os.path.join(output_dir, 'index.json')
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def update_index(entry, output_dir):
    """把一部规章的元数据写入 index.json（按 title 去重）。"""
    index = [e for e in load_index(output_dir) if e.get('title') != entry.get('title')]
    index.append(entry)
    path = os.path.join(output_dir, 'index.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def already_fetched(title, output_dir):
    """断点续爬：同名规章已存在则跳过。"""
    return os.path.exists(os.path.join(output_dir, f"{safe_filename(title)}.json"))


def load_targets(path):
    """加载 targets.json 目标清单。"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
