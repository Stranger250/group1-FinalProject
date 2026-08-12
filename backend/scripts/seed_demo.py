"""示例数据（Phase1 E01 验收用）：插入 4 条手工示例题（单选/多选/判断/填空）。

运行：cd shudao/backend && python scripts/seed_demo.py
幂等：已有手工题则跳过。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.model.question import (
    Question,
    QuestionDifficulty,
    QuestionSource,
    QuestionStatus,
    QuestionType,
)

DEMO_QUESTIONS = [
    {
        "type": QuestionType.SINGLE,
        "content": "高处作业必须佩戴哪种劳动防护用品？",
        "options": ["A 安全帽", "B 安全带", "C 手套", "D 口罩"],
        "answer": "A",
        "analysis": "依据《中华人民共和国安全生产法》第四十四条，生产经营单位必须为从业人员提供劳动防护用品；高处作业首要佩戴安全帽防止坠落物伤害。",
        "knowledge_point": "高处作业",
        "difficulty": QuestionDifficulty.EASY,
        "source_law_title": "中华人民共和国安全生产法",
        "source_article_no": "第四十四条",
    },
    {
        "type": QuestionType.MULTIPLE,
        "content": "下列哪些属于特种作业人员，必须经专门培训持证上岗？",
        "options": ["A 电工", "B 焊工", "C 厨师", "D 保安"],
        "answer": "A,B",
        "analysis": "依据《中华人民共和国安全生产法》第三十条，特种作业人员（电工、焊工等）必须经专门的安全作业培训并取得相应资格方可上岗作业。",
        "knowledge_point": "特种作业",
        "difficulty": QuestionDifficulty.MEDIUM,
        "source_law_title": "中华人民共和国安全生产法",
        "source_article_no": "第三十条",
    },
    {
        "type": QuestionType.JUDGE,
        "content": "生产经营单位必须为从业人员提供符合国家标准或者行业标准的劳动防护用品。",
        "options": ["A 正确", "B 错误"],
        "answer": "A",
        "analysis": "依据《中华人民共和国安全生产法》第四十四条，该表述正确。",
        "knowledge_point": "劳动防护",
        "difficulty": QuestionDifficulty.EASY,
        "source_law_title": "中华人民共和国安全生产法",
        "source_article_no": "第四十四条",
    },
    {
        "type": QuestionType.FILL,
        "content": "《中华人民共和国安全生产法》确立的安全生产方针是____、____。（两空，用分号分隔作答）",
        "options": None,
        "answer": "安全第一;预防为主",
        "analysis": "依据《中华人民共和国安全生产法》第三条，安全生产工作坚持安全第一、预防为主、综合治理的方针。",
        "knowledge_point": "安全生产方针",
        "difficulty": QuestionDifficulty.EASY,
        "source_law_title": "中华人民共和国安全生产法",
        "source_article_no": "第三条",
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        cnt = db.scalar(
            select(func.count(Question.id)).where(Question.source == QuestionSource.MANUAL)
        ) or 0
        if cnt > 0:
            print(f"[SKIP] 已有 {cnt} 条手工题，跳过示例数据")
            return
        for d in DEMO_QUESTIONS:
            db.add(
                Question(
                    **d,
                    source=QuestionSource.MANUAL,
                    status=QuestionStatus.APPROVED,
                    sources=None,
                    interference_verified=0,
                )
            )
        db.commit()
        print(f"[OK] 插入示例题 {len(DEMO_QUESTIONS)} 条（单选/多选/判断/填空）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
