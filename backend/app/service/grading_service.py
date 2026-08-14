"""自动阅卷（E05）纯评分模块：无 DB 依赖，可单测、可被 E06 统计复用。

判分口径对齐 DATABASE.md §6.1 题型作答约定与 question_service._validate_answers /
gen_service 入库约定（FILL 不转大写、其余 upper），保证入库答案与判分口径不漂移。
"""
from __future__ import annotations

# 全角 U+FF01-FF5E → 半角 U+0021-007E（含字母/数字/标点），全角空格 U+3000 → 半角空格。
# 中文输入法全角模式作答 'Ａ'/'，' 等若不归一，upper 后仍 ≠ 半角标签，被判 0 分（#11）。
_FULLWIDTH_MAP = {0xFF01 + i: 0x21 + i for i in range(94)}
_FULLWIDTH_MAP[0x3000] = 0x20


def _to_halfwidth(s: str) -> str:
    return s.translate(_FULLWIDTH_MAP)


def canonicalize(type_: str, raw: str | None) -> str:
    """归一化为存储/比对用串（幂等）。

    - 先全角→半角（字母/数字/标点/空格），再整体去首尾空格；空输入 → 空串；
    - FILL：全角分号 '；'→';'，按 ';' split 每空 strip【不转大写】，再以 ';' join；
    - SUBJECTIVE：同 FILL 的分号归一，但【保留原文大小写与内部空白】（解答题按要点包含判分）；
    - SINGLE/MULTIPLE/JUDGE：全角逗号 '，'→','；
      MULTIPLE 再 split 逐段 strip+upper、去空段、set 去重排序后以 ',' join；
      SINGLE/JUDGE 整体 upper。
    """
    if raw is None:
        return ""
    s = _to_halfwidth(str(raw)).strip()
    if not s:
        return ""
    if type_ in ("FILL", "SUBJECTIVE"):
        # 解答题参考答案用分号分隔多个要点，判分按要点包含（不转大写）
        return ";".join(b.strip() for b in s.replace("；", ";").split(";"))
    s = s.replace("，", ",")
    if type_ == "MULTIPLE":
        parts = [p.strip().upper() for p in s.split(",")]
        parts = [p for p in parts if p]
        return ",".join(sorted(set(parts)))  # 顺序无关、重复标签坍缩
    return s.upper()


def grade(type_: str, user_raw: str | None, correct_raw: str | None, full_score: int) -> tuple[int, int]:
    """判分：返回 (is_correct, score)。

    - SINGLE / JUDGE：精确相等（未作答/作答非 A、B → 判错）；
    - MULTIPLE：集合完全一致才得分，漏选/错选/多选/空答一律 0（PRD E05『全对得分』）；
    - FILL：空数必须一致 + 逐空完全匹配才得分，多填/少填/任一空不匹配 0；
    - SUBJECTIVE（解答题）：参考答案分号分隔多个要点，作答【包含】某要点即得该要点分，
      得分 = 命中要点数 / 总要点数 × 满分（四舍五入）；全命中 is_correct=1，未作答 0 分。
    """
    user = canonicalize(type_, user_raw)
    correct = canonicalize(type_, correct_raw)
    if type_ == "SUBJECTIVE":
        if not user or not correct:
            return (0, 0)
        points = [p for p in correct.split(";") if p]
        if not points:
            return (0, 0)
        hit = sum(1 for p in points if p in user)
        score = round(full_score * hit / len(points))
        return (1, score) if hit == len(points) else (0, score)
    if type_ == "FILL":
        ok = user == correct
    elif type_ == "MULTIPLE":
        ok = bool(user) and user == correct
    else:  # SINGLE / JUDGE
        ok = bool(user) and user == correct
    return (1, full_score) if ok else (0, 0)
