"""O11 文档上传解析：txt/md/pdf/docx → 纯文本（会话级临时上下文）。

校验口径（PRD O11）：
- 扩展名 + MIME 白名单：.txt/.md/.pdf/.docx；
- 大小上限 ≤10MB（读入内存校验，超限 400）；
- 魔数校验：PDF %PDF-、DOCX PK（zip），文本类按 UTF-8/GBK 容错解码；
- 输出截断 8000 字（与 ChatIn.file_context max_length 一致），超长保留头部；
- 不落盘（解析结果仅作请求体回传，由前端携带发送）。
"""
from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

_ALLOWED_EXTS = {".txt", ".md", ".pdf", ".docx"}
_ALLOWED_MIMES = {
    "text/plain", "text/markdown", "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",  # 部分浏览器/代理上传 txt 时给通用 MIME，魔数兜底
}
_MAX_CHARS = 8000
_MAX_BYTES = 10 * 1024 * 1024


def _check_magic(suffix: str, data: bytes) -> None:
    """魔数校验：PDF 以 %PDF- 开头；docx 为 ZIP（PK\x03\x04）；文本类跳过（容错解码）。"""
    if suffix == ".pdf" and not data[:5] == b"%PDF-":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="文件内容与扩展名不符（非 PDF）")
    if suffix == ".docx" and data[:4] != b"PK\x03\x04":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="文件内容与扩展名不符（非 docx）")


def _decode_text(data: bytes) -> str:
    """文本解码：优先 UTF-8，失败回退 GBK（国内公文常见），再失败 latin-1 兜底。"""
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def parse_upload(file: UploadFile) -> dict:
    """校验并解析上传文档，返回 {filename, ext, chars, text}。

    失败抛 400（类型/大小/解析失败）。text 已截断 ≤8000 字。
    """
    filename = file.filename or "未命名文件"
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in _ALLOWED_EXTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"仅支持 txt/md/pdf/docx 文档，收到 {suffix or '未知类型'}",
        )
    if (file.content_type or "") not in _ALLOWED_MIMES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"不支持的文件类型：{file.content_type}",
        )

    data = file.file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="文档超过大小上限（10MB）")
    if len(data) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="文件内容为空")

    _check_magic(suffix, data)

    try:
        if suffix == ".pdf":
            import pdfplumber
            with pdfplumber.open(_open_pdf(data)) as pdf:
                text = "\n".join(
                    (page.extract_text() or "") for page in pdf.pages
                ).strip()
        elif suffix == ".docx":
            import io
            from docx import Document
            doc = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
        else:
            text = _decode_text(data).strip()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 —— 解析失败统一 400
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"文档解析失败：{exc}")

    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="未能从文档中提取到文本（可能为扫描件）")

    truncated = len(text) > _MAX_CHARS
    if truncated:
        text = text[:_MAX_CHARS]
    return {
        "filename": filename,
        "ext": suffix.lstrip("."),
        "chars": len(text),
        "truncated": truncated,
        "text": text,
    }


def _open_pdf(data: bytes):
    """pdfplumber.open 需要文件对象：内存字节 → BytesIO。"""
    import io
    return io.BytesIO(data)
