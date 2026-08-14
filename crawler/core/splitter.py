# -*- coding: utf-8 -*-
"""
条款拆分：把规章全文按"第X章 / 第X条"拆成结构化 chapters[]。
这是爬虫最核心的复用件，输出直接喂 RAG 分块与 AI 出题。

输出结构：
  chapters = [ {"chapter": "第一章 总则",
                "articles": [ {"no": "第一条", "content": "……"} ] } ]
无章结构的规章整体归入一个"正文"章。
"""
import re

_CHAPTER_RE = re.compile(r'^第([一二三四五六七八九十百千万零〇0-9０-９]+)章\s*(.*)$')
_ARTICLE_RE = re.compile(r'^第([一二三四五六七八九十百千万零〇0-9０-９]+)条\s*')
# 可能出现的"章标题"但没按"第X章"写（少见，兜底）
_NAMED_CHAPTERS = ('总则', '附则', '分则', '通则')


def split_law_text(text):
    """把规章全文切成 chapters[]。text 为清洗后的纯文本。"""
    chapters = []
    current_chapter = None
    current_article = None

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # —— 章标题：第X章 ——
        m = _CHAPTER_RE.match(line)
        if m:
            current_chapter = {
                "chapter": f"第{m.group(1)}章 {m.group(2)}".strip(),
                "articles": [],
            }
            chapters.append(current_chapter)
            current_article = None
            continue

        # —— 章标题兜底：独立的"总则/附则"行 ——
        if line in _NAMED_CHAPTERS:
            current_chapter = {"chapter": line, "articles": []}
            chapters.append(current_chapter)
            current_article = None
            continue

        # —— 条：第X条 ——
        m = _ARTICLE_RE.match(line)
        if m:
            article = {"no": f"第{m.group(1)}条",
                       "content": line[m.end():].strip()}
            # 还没出现章 → 归入隐式"正文"章
            if current_chapter is None:
                current_chapter = {"chapter": "正文", "articles": []}
                chapters.append(current_chapter)
            current_chapter["articles"].append(article)
            current_article = article
            continue

        # —— 续行：把不是条头的行并入当前条末尾（跨行条文）——
        if current_article is not None:
            if current_article["content"]:
                current_article["content"] += line
            else:
                current_article["content"] = line

    # 清理：去掉空条；没有条的空章不保留
    result = []
    for ch in chapters:
        articles = [a for a in ch["articles"] if a["content"].strip()]
        if articles:
            result.append({"chapter": ch["chapter"], "articles": articles})
    return result


def count_articles(chapters):
    """统计总条款数（调试用）。"""
    return sum(len(ch["articles"]) for ch in chapters)
