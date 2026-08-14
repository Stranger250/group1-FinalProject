"""E02 AI 出题 Prompt 构造（对齐 AI_SOLUTION §6.2 出题 Prompt 设计 / §6.3 输出 JSON 结构）。

build_generate_prompt 依据检索条款、题型数量、难度、知识点拼装 (system, user)，供
llm_client.chat_json 调用。

题型数量分配约定：
- count >= len(types)：各题型按 count 均分、至少各 1 道，余数顺次加给靠前的题型；
- count < len(types)：按 types 顺序取前 count 类，每类 1 道（避免不足题数）。
"""
from __future__ import annotations

import json

# 输出 JSON 中要求的大写枚举，与 DATABASE.md §6.1 / schema.question 保持一致
_TYPES = "SINGLE | MULTIPLE | JUDGE | FILL"
_DIFFICULTY = "EASY | MEDIUM | HARD"
_SOURCE_ROLES = "answer | distractor | analysis"


def _allocate(types: list[str], count: int) -> list[tuple[str, int]]:
    """把 count 道题分配到各题型，返回 [(题型, 数量), …]。

    题型顺序保持传入顺序；余数优先分配给靠前的题型。
    """
    n = len(types)
    if n == 0:
        raise ValueError("题型列表不能为空")
    if count < 1:
        raise ValueError("count 必须 >= 1")
    if count < n:
        return [(t, 1) for t in types[:count]]
    base, extra = divmod(count, n)
    return [(t, base + (1 if i < extra else 0)) for i, t in enumerate(types)]


def _json_schema() -> str:
    """输出 JSON 结构的示例（字段对齐 AI_SOLUTION §6.3，type/difficulty 大写）。"""
    return (
        '{\n'
        '  "questions": [\n'
        '    {\n'
        '      "type": "SINGLE | MULTIPLE | JUDGE | FILL",\n'
        '      "content": "题干",\n'
        '      "options": ["A 选项", "B 选项", "C 选项", "D 选项"]（FILL 填空时为 null）,\n'
        '      "answer": "A"（多选 "A,C"，判断 "A"/"B"，填空多空用分号;分隔）,\n'
        '      "analysis": "答案解析，说明条款依据",\n'
        '      "knowledge_point": "知识点",\n'
        '      "difficulty": "EASY | MEDIUM | HARD",\n'
        '      "source_law_title": "主要依据法规名称",\n'
        '      "source_article_no": "主要依据条文号，如 第五十条",\n'
        '      "sources": [\n'
        '        {"role": "answer", "law_title": "法规名称", "article_no": "条文号"},\n'
        '        {"role": "distractor", "law_title": "法规名称", "article_no": "条文号"},\n'
        '        {"role": "analysis", "law_title": "法规名称", "article_no": "条文号"}\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        '}'
    )


def _format_articles(articles: list[dict]) -> str:
    """把检索条款格式化为 prompt 文本（每条带法规名/条号/正文），供出题与重写复用。"""
    if articles:
        lines = []
        for i, art in enumerate(articles, 1):
            law_title = (art.get("law_title") or "").strip()
            article_no = (art.get("article_no") or "").strip()
            content = (art.get("content") or "").strip()
            head = "｜".join(x for x in (law_title, article_no) if x)
            lines.append(f"{i}. 【{head}】\n{content}")
        return "\n\n".join(lines)
    return "（未检索到相关条款，请结合通用安全生产知识出题，并如实标注溯源）"


def build_generate_prompt(
    knowledge_point: str,
    articles: list[dict],
    types: list[str],
    difficulty: str,
    count: int,
    *,
    allocation: list[tuple[str, int]] | None = None,
    reference_text: str | None = None,
    reference_title: str | None = None,
) -> tuple[str, str]:
    """构造出题 Prompt，返回 (system, user)。

    - knowledge_point：知识点，必填（提供 reference_text 时可用文档限定出题范围）；
    - articles：检索到的条款列表，每项含 law_title / article_no / content；
    - types：题型列表（SINGLE/MULTIPLE/JUDGE/FILL），按序分配数量；
    - difficulty：难度（EASY/MEDIUM/HARD），统一转大写；
    - count：总题数（约定 >= 5，见 AI_SOLUTION §6 / settings.gen_min_count）；
    - allocation（keyword-only）：显式题型配额 [(type, n), …]（分轮生成时传入本轮配额，
      各轮求和即全局配额）；缺省按 _allocate(types, count) 自动分配，输出与旧版完全一致（回归安全）；
    - reference_text/reference_title（keyword-only）：上传参考文档的文本与文件名，
      有值时在 user prompt 插入【参考文档】块限定本次出题范围，并追加出题要求 8-10；
      缺省时输出与旧版完全一致（回归安全）。
    """
    knowledge_point = (knowledge_point or "").strip()
    if not knowledge_point:
        raise ValueError("knowledge_point 不能为空")
    if not types:
        raise ValueError("题型列表不能为空")
    if count < 1:
        raise ValueError("count 必须 >= 1")
    difficulty = difficulty.strip().upper()

    # 显式配额（分轮生成传本轮配额）优先；缺省按 (types, count) 自动分配，保证旧版输出不变
    plan = allocation if allocation is not None else _allocate(types, count)
    allocation_text = "；".join(f"{t} {c} 道" for t, c in plan)

    # 检索到的条款：每条带 law_title / article_no / content
    articles_text = _format_articles(articles)

    # 参考文档：有上传内容时插入出题范围块 + 追加出题要求 8-10
    ref_text = (reference_text or "").strip()
    ref_title = (reference_title or "").strip() or "上传参考文档"
    ref_block = ""
    ref_rules = ""
    if ref_text:
        ref_block = f"\n\n【参考文档（上传内容，限定了本次出题范围）】\n{ref_text}"
        ref_rules = (
            f"8. 出题内容以【参考文档】为准（它限定了本次出题的范围与考点），"
            f"每道题应在参考文档中找到内容依据。\n"
            f"9. 若【参考文档】与【法规条款】不一致，判定答案以法规条款为准，并在解析中说明依据。\n"
            f"10. 溯源 sources 优先引【法规条款】；若某题依据主要来自参考文档，"
            f"source_law_title 填「{ref_title}」的值，"
            f"source_article_no 填（上传参考文档）。\n"
        )

    if ref_text:
        # 有参考文档：文档与法规条款共同作为出题依据
        system = (
            "你是一名资深安全培训专家，精通安全生产、消防、职业健康、道路交通安全等法律法规，"
            "擅长严格依据法规原文出题。你必须以给定的法规条款与参考文档为出题依据，"
            "禁止凭空编造条文内容；"
            "确保每道题的题干、选项、答案与解析都能在条款中找到依据，且答案唯一正确。"
            "你只输出 JSON，不要 Markdown，不要额外说明。"
        )
    else:
        system = (
            "你是一名资深安全培训专家，精通安全生产、消防、职业健康、道路交通安全等法律法规，"
            "擅长严格依据法规原文出题。你必须以给定的法规条款为唯一依据，禁止凭空编造条文内容；"
            "确保每道题的题干、选项、答案与解析都能在条款中找到依据，且答案唯一正确。"
            "你只输出 JSON，不要 Markdown，不要额外说明。"
        )

    user = (
        f"【任务】请为「{knowledge_point}」知识点生成 {count} 道安全生产考试题，难度：{difficulty}。\n\n"
        f"【检索到的法规条款】\n{articles_text}"
        f"{ref_block}\n\n"
        f"【题型与数量】\n{allocation_text}。\n\n"
        f"【出题要求】\n"
        f"1. 每道题严格依据上述条款出题，题干可适度情境化，但答案与解析必须有条款依据；"
        f"解析需说明所依据的条款内容。\n"
        f"2. 干扰项从其他条款或其他安全常识构造，要求似是而非、有区分度，"
        f"避免明显错误、搞笑或过于绝对/宽泛的选项。\n"
        f"3. 判断题固定选项 [\"A 正确\",\"B 错误\"]；填空题 options 置 null，"
        f"多空答案用分号（;）分隔；单选答案为大写选项标签（如 A）；"
        f"多选答案为大写标签用英文逗号连接（如 A,C）。\n"
        f"4. type 必须为大写 {_TYPES} 之一；difficulty 必须为大写 {_DIFFICULTY} 之一。\n"
        f"5. 每题必须给出溯源 sources（数组，每项含 role/law_title/article_no，"
        f"role 取 {_SOURCE_ROLES}）：answer 标注正确选项依据的条款，"
        f"distractor 标注干扰项依据的条款（确无直接条文依据时可缺省该条），"
        f"analysis 标注解析依据的条款；answer 与 analysis 至少各一条。\n"
        f"6. 每题 source_law_title / source_article_no 为本题主要依据，"
        f"必须与 sources 中 answer（或 analysis）项的 law_title / article_no 一致。\n"
        f"7. 知识点统一填「{knowledge_point}」，难度填 {difficulty}。\n"
        f"{ref_rules}\n"
        f"【输出 JSON 结构（严格按此结构，不要增减字段）】\n{_json_schema()}\n\n"
        f"只输出 JSON，不要 Markdown，不要额外说明。"
    )
    return system, user


def _dump_question(original: dict) -> str:
    """把原题序列化为 JSON 文本（仅取重写所需字段，避免无关字段入 prompt）。"""
    keys = (
        "type", "content", "options", "answer", "analysis",
        "knowledge_point", "difficulty", "source_law_title", "source_article_no",
    )
    return json.dumps({k: original.get(k) for k in keys}, ensure_ascii=False, indent=2)


def _rewrite_json_schema() -> str:
    """重写输出 JSON 结构（单题对象，不含 questions 包裹）。"""
    return (
        '{\n'
        '  "type": "SINGLE | MULTIPLE | JUDGE | FILL",\n'
        '  "content": "修订后题干",\n'
        '  "options": ["A 选项", "B 选项", "C 选项", "D 选项"]（FILL 填空时为 null）,\n'
        '  "answer": "A"（多选 "A,C"，判断 "A"/"B"，填空多空用分号;分隔）,\n'
        '  "analysis": "答案解析，说明条款依据",\n'
        '  "knowledge_point": "知识点（保持与原题一致）",\n'
        '  "difficulty": "EASY | MEDIUM | HARD",\n'
        '  "source_law_title": "主要依据法规名称",\n'
        '  "source_article_no": "主要依据条文号",\n'
        '  "sources": [{"role": "answer|distractor|analysis", "law_title": "法规名称", "article_no": "条文号"}]\n'
        '}'
    )


def build_rewrite_prompt(
    original: dict,
    review_note: str,
    feedback: str,
    articles: list[dict],
) -> tuple[str, str]:
    """构造重写 Prompt（E02 增强，方案B），返回 (system, user)。

    - original：原题 dict（含 content/type/options/answer/analysis/knowledge_point/difficulty/sources）；
    - review_note：原题被驳回的审核意见（可为空）；
    - feedback：本次修订要求（必填）；
    - articles：检索到的法规条款（每条含 law_title/article_no/content）。
    """
    kp = (original.get("knowledge_point") or "").strip()
    qtype = (original.get("type") or "").strip()
    original_json = _dump_question(original)
    articles_text = _format_articles(articles)
    review_line = (review_note or "").strip() or "（无）"

    system = (
        "你是一名资深安全培训专家，精通安全生产、消防、职业健康、道路交通安全等法律法规，"
        "擅长严格依据法规原文出题。本次任务是修订一道被审核驳回的考试题："
        "必须以给定的法规条款为唯一依据，禁止凭空编造条文内容；"
        "以「驳回原因」和「修订要求」为权威指令逐条修改，"
        "若原答案与条款冲突必须以条款为准重新判定。你只输出 JSON，不要 Markdown，不要额外说明。"
    )

    user = (
        f"【待修订原题】\n{original_json}\n\n"
        f"【驳回原因】\n{review_line}\n\n"
        f"【本次修订要求】\n{feedback}\n\n"
        f"【检索到的法规条款】\n{articles_text}\n\n"
        f"【修订要求】\n"
        f"1. 依据「驳回原因」与「本次修订要求」逐条修改题目；若原答案与条款冲突，以条款为准重新判定正确答案。\n"
        f"2. 题型 type 必须保持「{qtype}」不变；知识点保持「{kp}」不变；"
        f"难度 difficulty 除非修订要求明确要求调整，否则保持原难度。\n"
        f"3. 题干、选项、答案、解析必须齐全；判断题固定选项 [\"A 正确\",\"B 错误\"]；"
        f"填空题 options 置 null，多空答案用分号（;）分隔；单选答案为选项标签（如 A），"
        f"多选为逗号连接的大写标签（如 A,C）。\n"
        f"4. 必须实质修改（仅措辞润色不算修订），确保修订版解决了驳回问题。\n"
        f"5. 每项溯源 sources（role 取 answer|distractor|analysis）必须在给定条款范围内，"
        f"source_law_title / source_article_no 与 sources 中 answer 项一致。\n"
        f"6. 直接输出一个修订后的题目对象（不要包在 questions 数组里）：\n"
        f"{_rewrite_json_schema()}\n\n"
        f"只输出 JSON，不要 Markdown，不要额外说明。"
    )
    return system, user


def _format_blocks(blocks: list) -> str:
    """把检索块格式化为 prompt 参考资料（[n] 与引用卡片序号一一对应）。

    blocks 为 RetrievedBlock 列表；出处头 = 标题 + 条号（章头块无条号只给标题）。
    """
    lines = []
    for i, b in enumerate(blocks, 1):
        head = "｜".join(x for x in (b.title, b.article_no) if x)
        lines.append(f"{i}. 【{head}】\n{b.content}")
    return "\n\n".join(lines)


def build_qa_prompt(
    blocks: list,
    history: list[str],
    query: str,
    mode: str,
    *,
    max_tokens: int = 800,
    conservative_tokens: int = 300,
) -> tuple[str, str, int]:
    """构造问答 Prompt（A01 RAG 智能问答），返回 (system, user, max_tokens)。

    - blocks：检索返回的父块列表（RetrievedBlock，含 title/article_no/content）；
    - history：历史 user 问句（时间正序，最近的几轮）；
    - query：当前用户问题（原文，非改写串——改写只用于检索）；
    - mode：full/conservative——conservative 收紧 max_tokens（防过度发挥）。
    system 五条硬约束：只依据资料、事实逐字出处标 [n]、禁库外编造、数值/条号原样复述、
    资料不足如实说明。引用脚注 [n] 由后端 grounding 校验（越界删除，缺失置 0）。
    """
    refs = _format_blocks(blocks)
    history_text = _format_history(history)
    limit = conservative_tokens if mode == "conservative" else max_tokens

    system = (
        "你是「蜀道安全助手」，一名精通安全生产、消防、职业健康等法律法规的 AI 助手。"
        "你只能依据下方【参考资料】中的条文原文回答用户关于安全生产法规的问题。"
        "必须遵守以下硬约束：\n"
        "1. 仅依据【参考资料】作答，严禁使用库外知识或凭空编造条文内容；"
        "资料不足以回答时，如实说明「资料中没有查到明确依据」。\n"
        "2. 涉及事实、数据、处罚金额、时限、条号等必须严格对应资料原文，数值和条号逐字原样复述，不得换算、凑整或改写。\n"
        "3. 引用某条资料时在对应句末用脚注标注 [n]，n 为【参考资料】中的条目序号；"
        "引用哪条资料就标哪个号，不得标注未使用的资料，也不得编造不存在的序号。\n"
        "4. 若用户问的是与安全生产无关的寒暄，可简短礼貌回应；"
        "若是模糊或非法的问题，先说明无法回答。\n"
        "5. 用简体中文回答，结构清晰、条理分明，直接给出结论再解释依据。"
    )

    user = f"【参考资料】\n{refs}\n\n{history_text}【问题】\n{query}\n\n请依据【参考资料】回答上述问题，引用出处时标注 [n]。"
    return system, user, limit


def _format_history(history: list[str]) -> str:
    """历史 user 问句摘要（至多 5 轮，无历史返回空串）。"""
    if not history:
        return ""
    lines = []
    for i, q in enumerate(history, 1):
        lines.append(f"第{i}轮：{q}")
    return "【对话历史】\n" + "\n".join(lines) + "\n\n"
