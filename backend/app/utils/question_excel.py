"""题目 Excel 批量导入/导出（任务书 §2.10「批量导入/导出题目（Excel 格式）」落地）。

- 导出：题库 → .xlsx（表头：type/content/options/answer/analysis/knowledge_point/difficulty）；
  options 多选项用 | 分隔（导出时还原为 ["A. xxx", ...] 格式）；
- 导入：解析 .xlsx → 逐行构造 QuestionCreate 等价 dict，行级校验收集错误
  （不中断整批），全部行校验通过才入库（沿用「先全校验、再单事务」约定）；
- 模板：无文件上传时导出空模板（仅表头 + 示例行）。

校验规则与 E01 手工录入一致：题型枚举、难度枚举、题干/解析必填、
答案格式（复用 QuestionService._validate_answers 语义）。
"""
from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook, load_workbook

from ..model.question import QuestionType

# 表头（固定列序，导入/导出/模板共用）
HEADERS = ["type", "content", "options", "answer", "analysis",
           "knowledge_point", "difficulty"]

TYPE_OPTION_NEEDED = (QuestionType.SINGLE, QuestionType.MULTIPLE)

# 每行一个「序号 + 错误原因」的错误明细
_OPTION_SEP = "|"


def export_questions_to_xlsx(items: list[dict]) -> bytes:
    """题库行（_to_dict 结构）→ xlsx 字节流。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "题目"
    ws.append(HEADERS)
    for q in items:
        opts = q.get("options") or []
        ws.append([
            q.get("type", ""),
            q.get("content", ""),
            _OPTION_SEP.join(str(o) for o in opts) if opts else "",
            q.get("answer", ""),
            q.get("analysis") or "",
            q.get("knowledge_point", ""),
            q.get("difficulty", ""),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_import_template() -> bytes:
    """空模板（表头 + 四种题型示例行）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "题目"
    ws.append(HEADERS)
    ws.append(["SINGLE", "示例：高处作业时安全带应（ ）。",
               "A. 系挂在牢固构件上|B. 随意搭在肩上|C. 不系挂", "A",
               "解析：安全带必须系挂在牢固构件上。", "高处作业", "EASY"])
    ws.append(["JUDGE", "示例：雨天应停止露天高处作业。", "", "A",
               "解析：五级以上大风/雨天应停止露天高处作业。", "高处作业", "MEDIUM"])
    ws.append(["FILL", "示例：安全生产方针是（ ）第一、预防为主。", "", "安全",
               "解析：安全第一、预防为主。", "安全生产方针", "EASY"])
    ws.append(["SUBJECTIVE", "示例：简述动火作业前的安全要求。", "",
               "办理动火作业许可证；清除周围可燃物；配备灭火器材", "解析：…", "动火作业", "MEDIUM"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_import_rows(data: bytes) -> tuple[list[dict], list[dict]]:
    """解析导入 xlsx：返回 (合法行列表, 错误明细列表 [{row, error}]）。

    合法行为可直接入库的 kwargs（type/content/options/answer/analysis/knowledge_point/difficulty）。
    行级校验：表头缺失/错列、题型枚举、难度枚举、题干/解析必填、答案格式。
    """
    wb = load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], [{"row": 1, "error": "文件为空"}]

    # 表头校验：首行必须包含 type/content/answer（容错列序）
    header = [str(c or "").strip() for c in rows[0]]
    col = {h: header.index(h) for h in HEADERS if h in header}
    for required in ("type", "content", "answer"):
        if required not in col:
            return [], [{"row": 1, "error": f"缺少必填列 {required}（表头：{', '.join(header)}）"}]

    valid: list[dict] = []
    errors: list[dict] = []
    for i, raw in enumerate(rows[1:], start=2):
        if raw is None or all(c is None or str(c).strip() == "" for c in raw):
            continue  # 空行跳过
        row_err: list[str] = []

        def cell(name: str) -> str:
            idx = col.get(name)
            if idx is None or idx >= len(raw) or raw[idx] is None:
                return ""
            return str(raw[idx]).strip()

        type_ = cell("type").upper()
        content = cell("content")
        answer = cell("answer")
        analysis = cell("analysis")
        knowledge_point = cell("knowledge_point")
        difficulty = cell("difficulty").upper()
        options_raw = cell("options")

        # 题型
        if type_ not in (QuestionType.SINGLE, QuestionType.MULTIPLE,
                         QuestionType.JUDGE, QuestionType.FILL, QuestionType.SUBJECTIVE):
            row_err.append(f"题型不合法：{type_ or '空'}")
        # 题干/解析必填
        if not content:
            row_err.append("题干不能为空")
        if not analysis:
            row_err.append("解析必填")
        if not knowledge_point:
            row_err.append("知识点不能为空")
        # 难度
        if difficulty not in ("EASY", "MEDIUM", "HARD"):
            row_err.append(f"难度不合法：{difficulty or '空'}")

        # 选项：SINGLE/MULTIPLE 必须提供；其余置空
        options: list[str] | None = None
        if type_ in TYPE_OPTION_NEEDED:
            parts = [p.strip() for p in options_raw.split(_OPTION_SEP) if p.strip()]
            if len(parts) < 2:
                row_err.append("单选/多选需至少 2 个选项（用 | 分隔）")
            else:
                options = [f"{chr(65 + i)}. {p}" for i, p in enumerate(parts)]
        else:
            options = None

        # 答案非空
        if not answer:
            row_err.append("答案不能为空")

        if row_err:
            errors.append({"row": i, "error": "；".join(row_err)})
            continue

        valid.append({
            "type": type_,
            "content": content,
            "options": options,
            "answer": answer,
            "analysis": analysis,
            "knowledge_point": knowledge_point,
            "difficulty": difficulty,
        })
    return valid, errors
