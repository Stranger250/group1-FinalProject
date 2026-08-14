"""E02 AI 出题参考文档文本提取（不落盘，前端上传 → 解析纯文本回传）。

支持 .txt/.md/.pdf/.docx 四种格式；pdf/docx 依赖库（pdfplumber / python-docx）延迟导入，
未安装时按需抛 ImportError，由调用方（app/api/ai.py）转 500。非法扩展名抛 ValueError
（消息含「不支持的文档类型」），由调用方转 400。
"""
from __future__ import annotations

import io
from pathlib import Path

# 支持的参考文档扩展名（小写，见 /doc 端点与 extract_text）
REF_DOC_EXTS = {".txt", ".md", ".pdf", ".docx"}


def _decode_text(data: bytes) -> str:
    """解码纯文本：先 utf-8 严格，失败再 gbk，再失败 utf-8 errors=replace 兜底。"""
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            return data.decode("gbk")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes) -> str:
    """pdfplumber 逐页提取文本；无文本页返回空串，最终按页换行拼接。"""
    import pdfplumber  # 延迟导入：未装依赖时按需报错

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _extract_docx(data: bytes) -> str:
    """python-docx 提取段落文本，按段换行拼接。"""
    import docx  # 延迟导入：未装依赖时按需报错

    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs)


def extract_text(filename: str, data: bytes) -> str:
    """按扩展名（小写）提取文档纯文本。

    非法扩展名抛 ValueError（消息含「不支持的文档类型」）。
    """
    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md"):
        return _decode_text(data)
    if ext == ".pdf":
        return _extract_pdf(data)
    if ext == ".docx":
        return _extract_docx(data)
    raise ValueError(f"不支持的文档类型：{filename}（仅支持 {'/'.join(sorted(REF_DOC_EXTS))}）")
