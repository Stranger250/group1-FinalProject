"""规则多轮查询改写（用户决策：规则优先，零 LLM 调用）。

策略（RAG 方案 §2.3.2 / 多轮评测集 §5.4）：
  - 触发：当前问含指代词（它/该/那/此…），或轮次≥2 且问 ≤6 字（过短承接）；
  - 改写：最近 max_rounds 轮用户问句按序拼接（；分隔）+ 当前问，生成独立成句 query；
  - 检索层双路喂 BM25：改写后 query 与原文都进，`rewritten_used` 打标；
  - 返回 (rewritten_query, rewritten_used)，未触发时 rewritten_used=False。
"""
from __future__ import annotations

from dataclasses import dataclass

# 指代词（触发改写）
PRONOUNS = (
    "它", "这个", "那个", "这些", "那些", "上述", "上面", "刚才", "该条", "该规定",
    "那条", "这", "那", "此", "其", "该", "它们", "这条",
)

# 过短承接阈值（含问 ≤ 该长度则必然承接上轮）
_SHORT_QUESTION_CHARS = 6


@dataclass
class RewriteResult:
    query: str      # 改写后 query（未触发时 = 原文）
    rewritten_used: bool


def _contains_pronoun(q: str) -> bool:
    return any(p in q for p in PRONOUNS)


def should_rewrite(question: str, history_count: int) -> bool:
    if _contains_pronoun(question):
        return True
    if history_count >= 2 and len(question) <= _SHORT_QUESTION_CHARS:
        return True
    return False


def rewrite_query(question: str, history_questions: list[str], max_rounds: int = 5) -> RewriteResult:
    """history_questions：历史 user 问句（时间正序）。改写 = 最近几轮拼接 + 当前问。"""
    if not should_rewrite(question, len(history_questions)):
        return RewriteResult(query=question, rewritten_used=False)
    parts = [q for q in history_questions[-max_rounds:] if q]
    parts.append(question)
    return RewriteResult(query="；".join(parts), rewritten_used=True)
