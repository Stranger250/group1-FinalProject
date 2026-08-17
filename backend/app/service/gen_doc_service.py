"""O12 文档生成服务：Word / PPT（DeepSeek 生成大纲 → python-docx / python-pptx 本地渲染）。

流程（PRD O12 §3）：
  ① 用户提交 {doc_type, topic, style?, pages?}；
  ② DeepSeek（现有 llm_client.chat_json，WPS 凭据不可用走降级路径）生成结构化大纲：
     Word: [{level, title, content}]；PPT: [{title, bullets:[...]}]（含封面/目录/要点/结束页 ≥8 页）；
  ③ 敏感词检查（命中 400）；
  ④ python-docx / python-pptx 渲染（纯本地，不依赖 WPS 客户端）；
  ⑤ 留审计 doc_generate（类型/标题/用户/页数）。

实现说明（对齐 PRD「API 实测记录 2026-08-17」）：WPS apik 换 token 被服务端拒绝（400 UnknownError，
疑似未授权），故本服务直接走 DeepSeek 降级路径（PRD 允许：失败自动降级，功能不中断）。
"""
from __future__ import annotations

import io
import json
import logging
import re

from fastapi import HTTPException

from ..ai.llm_client import LLMError, chat_json
from ..rag.sensitive import contains_sensitive

logger = logging.getLogger("rag.gendoc")

DOC_TYPES = ("word", "ppt")
_MAX_TOPIC = 200
_MAX_PAGES = 30

_SYSTEM_WORD = (
    "你是企业安全生产文档编写专家。根据用户主题生成 Word 文档大纲，"
    "输出严格 JSON（不要 markdown 围栏）："
    '{"title": "文档标题", "sections": [{"heading": "一、xxx", "paragraphs": ["段落1", "段落2"]}, ...]}。'
    "要求：标题层级清晰（1-3 级用 heading 深度体现）、内容具体可执行、总段落 8-20 段、"
    "贴合安全生产/施工管理场景。"
)

_SYSTEM_PPT = (
    "你是企业安全生产培训课件设计专家。根据用户主题生成 PPT 大纲，"
    "输出严格 JSON（不要 markdown 围栏）："
    '{"title": "课件标题", "slides": [{"title": "页标题", "bullets": ["要点1", "要点2", "要点3"]}, ...]}。'
    "要求：第一页为封面（title=主题）、第二页为目录、最后一页为结束页（谢谢/培训小结），"
    f"总页数 8-{_MAX_PAGES} 页、每页 2-5 条要点、内容贴合安全生产场景。"
)


def _extract_content(raw: str) -> str:
    """剥 markdown 围栏与首尾空白。"""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return text


async def generate_outline(doc_type: str, topic: str, style: str = "正式") -> dict:
    """① DeepSeek 生成大纲（返回结构化 dict）。"""
    style_hint = f"风格要求：{style}。" if style else ""
    system = _SYSTEM_PPT if doc_type == "ppt" else _SYSTEM_WORD
    user = f"主题：{topic}\n{style_hint}请直接输出 JSON 大纲。"
    try:
        raw = await chat_json(system, user, temperature=0.4)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"大纲生成失败（LLM）：{exc}")
    try:
        parsed = raw if isinstance(raw, dict) else json.loads(_extract_content(str(raw)))
        if not isinstance(parsed, dict):
            raise ValueError("大纲不是对象")
        return parsed
    except Exception as exc:  # noqa: BLE001
        logger.warning("大纲 JSON 解析失败: %s", exc)
        raise HTTPException(status_code=502, detail="大纲生成格式异常，请重试")


# ---------- Word 渲染 ----------

def _render_word(outline: dict) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    doc = Document()
    title = str(outline.get("title") or "安全生产文档").strip()
    doc.add_heading(title, level=0)

    sections = outline.get("sections") or []
    if not sections:
        # 兜底：无 sections 时以 title 为一级标题
        doc.add_paragraph(str(outline))
    for sec in sections:
        heading = str(sec.get("heading") or "").strip()
        if heading:
            doc.add_heading(heading, level=1)
        for para in (sec.get("paragraphs") or []):
            text = str(para).strip()
            if not text:
                continue
            p = doc.add_paragraph(text)
            p.paragraph_format.first_line_indent = Pt(24)  # 首行缩进两字符
            p.paragraph_format.line_spacing = 1.5
    # 页脚：页数
    footer = doc.sections[0].footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fp.add_run("— 蜀道安全助手生成 —")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------- PPT 渲染 ----------

def _render_ppt(outline: dict) -> bytes:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    title = str(outline.get("title") or "安全培训课件").strip()
    slides = outline.get("slides") or []
    # 兜底：不足 8 页补足（生成内容过短时）
    if len(slides) < 8:
        slides = slides + [
            {"title": f"补充内容 {i}", "bullets": ["详见培训材料", "结合实际案例讲解"]}
            for i in range(1, 8 - len(slides) + 1)
        ]

    for i, s in enumerate(slides[: _MAX_PAGES]):
        stitle = str(s.get("title") or f"第 {i + 1} 页").strip()
        bullets = [str(b).strip() for b in (s.get("bullets") or []) if str(b).strip()]

        slide = prs.slides.add_slide(blank)
        # 顶部标题条
        box = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(12.1), Inches(0.9))
        tf = box.text_frame
        tf.text = stitle
        p = tf.paragraphs[0]
        p.font.size = Pt(30)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0x1E, 0x5A, 0x52)  # 蜀道青绿
        p.alignment = PP_ALIGN.LEFT

        # 要点区
        body = slide.shapes.add_textbox(Inches(0.8), Inches(1.6), Inches(11.7), Inches(5.2))
        btf = body.text_frame
        btf.word_wrap = True
        for j, b in enumerate(bullets):
            para = btf.paragraphs[0] if j == 0 else btf.add_paragraph()
            para.text = f"• {b}"
            para.font.size = Pt(20)
            para.space_after = Pt(10)
        if not bullets:
            para = btf.paragraphs[0]
            para.text = "（内容待补充）"
            para.font.size = Pt(20)

        # 页脚
        foot = slide.shapes.add_textbox(Inches(0.6), Inches(7.0), Inches(12.1), Inches(0.4))
        ftf = foot.text_frame
        ftf.text = f"蜀道安全助手 · {i + 1}/{len(slides[: _MAX_PAGES])}"
        ftf.paragraphs[0].font.size = Pt(10)
        ftf.paragraphs[0].font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ---------- 入口 ----------

def render_document(doc_type: str, outline: dict) -> bytes:
    if doc_type == "ppt":
        return _render_ppt(outline)
    return _render_word(outline)
