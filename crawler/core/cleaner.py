# -*- coding: utf-8 -*-
"""
正文清洗：去掉页眉页脚、导航、发布时间行、多余空白。
针对政府规章全文页的常见噪音（页脚"第X页"、孤立页码、导航链接等）。
"""
import re


def clean_text(text):
    """清洗规章全文，返回干净的纯文本。"""
    if not text:
        return ""

    # 1. 去掉孤立页码行（如 "1"、"第 1 页"、"共 5 页"）
    text = re.sub(r'^\s*第?\s*\d+\s*页?\s*(?:/\s*\d+\s*页?)?\s*$',
                  '', text, flags=re.MULTILINE)

    # 2. 去掉"第X页/共X页"页脚（行尾）
    text = re.sub(r'[ \t]*第\s*\d+\s*页[ \t]*共\s*\d+\s*页', '', text)

    # 3. 去掉常见页眉页脚：来源/发布时间/发布机构行
    text = re.sub(r'^\s*(?:来源|发布机构|发布时间|发布日期|日期)[：:]\s*\S.*$',
                  '', text, flags=re.MULTILINE)

    # 4. 去掉导航关键词行（首页/上一页/下一篇/相关链接等）
    text = re.sub(r'^\s*(?:首页|上一页|下一页|上一篇|下一篇|返回顶部|相关链接|政策解读)\s*$',
                  '', text, flags=re.MULTILINE)

    # 5. 去掉"目 录"目录段（从"目 录/目录"到第一个"第X章"之间）
    m = re.search(r'^\s*目\s*录\s*\n(.*?)(?=^\s*第[一二三四五六七八九十百千万零〇0-9０-９]+章)',
                  text, flags=re.MULTILINE | re.DOTALL)
    if m:
        text = text[:m.start()] + text[m.end():]

    # 6. 去除词中空格（如"总 则"->"总则"、"目 录"->"目录"、"第 一 章"->"第一章"）
    #    仅处理常见规章词组，避免误伤正文中正常的空格排版
    text = re.sub(r'第\s+[一二三四五六七八九十百千万零〇0-9０-９]+\s+章', lambda m: m.group(0).replace(' ', ''), text)
    text = re.sub(r'第\s+[一二三四五六七八九十百千万零〇0-9０-９]+\s+条', lambda m: m.group(0).replace(' ', ''), text)
    for word in ('总则', '附则', '分则', '目录'):
        text = re.sub(rf'{word[0]}\s+{word[1]}', word, text)

    # 7. 合并多余空白行
    text = re.sub(r'[ \t　]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()
