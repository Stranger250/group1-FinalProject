"""建库脚本（Phase0）：执行 schema.sql 建全部表 + 初始化角色/管理员。

运行：cd shudao/backend && python scripts/init_db.py
前提：MySQL 服务已启动；backend/.env 的 DATABASE_URL 已填正确密码。
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.engine import make_url

# 保证可导入 app 包（从 backend 目录运行时 cwd 已在 sys.path，这里兜底）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymysql

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from app.core.config import get_settings
from app.core.security import hash_password

ROLES = [
    (1, "EMPLOYEE", "普通员工", "隐患上报/AI问答/参加考试"),
    (2, "SAFETY", "安全管理员", "隐患派单验收/题目审核/统计分析"),
    (3, "ADMIN", "系统管理员", "用户权限/系统配置"),
]


def parse_db_url(url: str):
    """解析 mysql+pymysql://user:pass@host:port/db?xxx。

    用 SQLAlchemy make_url 权威解析：正确进行 URL 解码（密码含 @/:/# 等特殊字符时，
    手写正则会在第一个 @ 处截断 → 密码错 → 1045 Access denied）。
    """
    u = make_url(url)
    if not u.username or not u.database:
        raise SystemExit(f"无法解析 DATABASE_URL：{url}")
    return u.username, u.password or "", u.host, u.port or 3306, u.database


def _migrate_question_rewrite(cur, db: str) -> bool:
    """E02 重写增强迁移（幂等）：question 表补齐 rewrite_of / rewrite_feedback / rewrite_pending。

    schema.sql 的 CREATE TABLE IF NOT EXISTS 不会给已存在的表补列，这里针对
    旧库做一次幂等 ALTER：逐列检查 information_schema，缺哪补哪。
    返回 True 表示执行了迁移。
    """
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='question'",
        (db,),
    )
    cols = {row[0] for row in cur.fetchall()}
    cur.execute(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='question'",
        (db,),
    )
    idxs = {row[0] for row in cur.fetchall()}

    migrated = False
    adds = []
    if "rewrite_of" not in cols:
        adds.append("ADD COLUMN rewrite_of BIGINT NULL")
    if "rewrite_feedback" not in cols:
        adds.append("ADD COLUMN rewrite_feedback VARCHAR(255) NULL")
    if "idx_rewrite_of" not in idxs:
        adds.append("ADD KEY idx_rewrite_of (rewrite_of)")
    if adds:
        cur.execute("ALTER TABLE question " + ", ".join(adds))
        migrated = True
    # 生成列引用 rewrite_of，需在 rewrite_of 已存在后再加（分两条 ALTER，避免同语句引用未建列）
    if "rewrite_pending" not in cols:
        cur.execute(
            "ALTER TABLE question "
            "ADD COLUMN rewrite_pending BIGINT GENERATED ALWAYS AS "
            "(IF(rewrite_of IS NULL, NULL, IF(status='PENDING', rewrite_of, NULL))) STORED"
        )
        migrated = True
    if "uk_rewrite_pending" not in idxs:
        cur.execute("ALTER TABLE question ADD UNIQUE KEY uk_rewrite_pending (rewrite_pending)")
        migrated = True
    return migrated


def _migrate_exam_paper(cur, db: str) -> bool:
    """E03 组卷迁移（幂等）：exam_paper 补齐 gen_mode / status 列 + idx_status 索引。

    schema.sql 的 CREATE TABLE IF NOT EXISTS 不会给已存在的表补列，这里针对
    旧库做一次幂等 ALTER。
    """
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='exam_paper'",
        (db,),
    )
    cols = {row[0] for row in cur.fetchall()}
    cur.execute(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='exam_paper'",
        (db,),
    )
    idxs = {row[0] for row in cur.fetchall()}

    migrated = False
    adds = []
    if "gen_mode" not in cols:
        adds.append("ADD COLUMN gen_mode VARCHAR(8) NOT NULL DEFAULT 'manual'")
    if "status" not in cols:
        adds.append("ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'DRAFT'")
    if adds:
        cur.execute("ALTER TABLE exam_paper " + ", ".join(adds))
        migrated = True
    if "idx_status" not in idxs:
        cur.execute("ALTER TABLE exam_paper ADD KEY idx_status (status)")
        migrated = True
    return migrated


def _migrate_exam_record(cur, db: str) -> bool:
    """E04/E05 迁移（幂等）：exam_record 补 state/cheat_count/submit_reason + 默认值 + 唯一键；
    exam_answer 放宽 user_answer/correct_answer 为 VARCHAR(255) + 补 uk_record_question 唯一键。

    - state：ONGOING/SUBMITTED 生命周期（刷新恢复、防重复开考、双交防护载体）；
    - uk_user_paper_ongoing：基于生成列 ongoing_key 的部分唯一（state='ONGOING' 时取
      user_id-paper_id，否则 NULL），DB 级保证同用户同试卷至多一条进行中，同时 SUBMITTED
      多条互不冲突 → 允许重考/多次交卷历史；
    - uk_record_question：(record_id,question_id) 唯一，是 INSERT..ON DUPLICATE KEY UPDATE 的锚点。
    """
    migrated = False
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='exam_record'",
        (db,),
    )
    rec_cols = {row[0] for row in cur.fetchall()}
    cur.execute(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='exam_record'",
        (db,),
    )
    rec_idxs = {row[0] for row in cur.fetchall()}

    adds = []
    if "state" not in rec_cols:
        adds.append("ADD COLUMN state VARCHAR(16) NOT NULL DEFAULT 'ONGOING'")
    if "cheat_count" not in rec_cols:
        adds.append("ADD COLUMN cheat_count INT NOT NULL DEFAULT 0")
    if "submit_reason" not in rec_cols:
        adds.append("ADD COLUMN submit_reason VARCHAR(16) NULL")
    if adds:
        cur.execute("ALTER TABLE exam_record " + ", ".join(adds))
        migrated = True
    if "end_time" in rec_cols:
        cur.execute("ALTER TABLE exam_record MODIFY COLUMN end_time DATETIME NULL")
        migrated = True
    if "score" in rec_cols:
        cur.execute("ALTER TABLE exam_record MODIFY COLUMN score INT NOT NULL DEFAULT 0")
        migrated = True
    if "status" in rec_cols:
        cur.execute("ALTER TABLE exam_record MODIFY COLUMN status VARCHAR(16) NOT NULL DEFAULT ''")
        migrated = True
    # 旧版唯一键基于 (user_id,paper_id,state)：同用户同试卷只能有一条 SUBMITTED，堵死重考 → 重建为生成列方案
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='exam_record' AND INDEX_NAME='uk_user_paper_ongoing'",
        (db,),
    )
    old_key_cols = {row[0] for row in cur.fetchall()}
    if old_key_cols and "state" in old_key_cols:
        cur.execute("ALTER TABLE exam_record DROP INDEX uk_user_paper_ongoing")
        rec_idxs.discard("uk_user_paper_ongoing")  # 更新内存快照，让下方重建
        migrated = True
    if "ongoing_key" not in rec_cols:
        cur.execute(
            "ALTER TABLE exam_record ADD COLUMN ongoing_key VARCHAR(40) "
            "GENERATED ALWAYS AS (IF(state = 'ONGOING', CONCAT(user_id, '-', paper_id), NULL)) STORED"
        )
        migrated = True
    if "uk_user_paper_ongoing" not in rec_idxs:
        cur.execute(
            "ALTER TABLE exam_record ADD UNIQUE KEY uk_user_paper_ongoing (ongoing_key)"
        )
        migrated = True

    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='exam_answer'",
        (db,),
    )
    ans_cols = {row[0] for row in cur.fetchall()}
    cur.execute(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='exam_answer'",
        (db,),
    )
    ans_idxs = {row[0] for row in cur.fetchall()}

    if "user_answer" in ans_cols:
        cur.execute("ALTER TABLE exam_answer MODIFY COLUMN user_answer VARCHAR(255) NOT NULL")
        migrated = True
    if "correct_answer" in ans_cols:
        cur.execute("ALTER TABLE exam_answer MODIFY COLUMN correct_answer VARCHAR(255) NOT NULL")
        migrated = True
    if "uk_record_question" not in ans_idxs:
        cur.execute(
            "ALTER TABLE exam_answer ADD UNIQUE KEY uk_record_question (record_id, question_id)"
        )
        migrated = True
    return migrated


def _migrate_ai_chat(cur, db: str) -> bool:
    """模块二 AI 助手迁移（幂等）：message 表补 feedback 列（A07 点赞/点踩）。

    语义：NULL=未反馈、1=有用、-1=没用、0=清除；单行 UPDATE 天然幂等。
    schema.sql 的 CREATE TABLE IF NOT EXISTS 不会给已存在的表补列，这里针对旧库做幂等 ALTER。
    """
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='message'",
        (db,),
    )
    cols = {row[0] for row in cur.fetchall()}
    if "feedback" in cols:
        return False
    cur.execute("ALTER TABLE message ADD COLUMN feedback TINYINT NULL")
    return True


def _migrate_message_source_source_loc(cur, db: str) -> bool:
    """模块二 AI 助手迁移（幂等）：message_source 补 doc_id/article_no 列（历史引用可点击查看原文）。

    历史 sources 缺原文定位 → 前端 normalizeStoredSource 一律 clickable=false（「无法点击查看来源」）。
    补列后新回答落库即带 doc_id/article_no，历史旧行保持 NULL（不可点击，不回填）。
    schema.sql 的 CREATE TABLE IF NOT EXISTS 不会给已存在的表补列，这里针对旧库做幂等 ALTER。
    """
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='message_source'",
        (db,),
    )
    cols = {row[0] for row in cur.fetchall()}
    adds = []
    if "doc_id" not in cols:
        adds.append("ADD COLUMN doc_id VARCHAR(64) NULL")
    if "article_no" not in cols:
        adds.append("ADD COLUMN article_no VARCHAR(64) NULL")
    if not adds:
        return False
    cur.execute("ALTER TABLE message_source " + ", ".join(adds))
    return True


def _migrate_user_profile(cur, db: str) -> bool:
    """个人中心迁移（幂等）：user 表补 email/avatar 列（T2 个人中心，无 email/头像的历史字段）。
    schema.sql 的 CREATE TABLE IF NOT EXISTS 不会给已存在的表补列，这里针对旧库做幂等 ALTER。
    """
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='user'",
        (db,),
    )
    cols = {row[0] for row in cur.fetchall()}
    adds = []
    if "email" not in cols:
        adds.append("ADD COLUMN email VARCHAR(120) NULL")
    if "avatar" not in cols:
        adds.append("ADD COLUMN avatar VARCHAR(255) NULL")
    if not adds:
        return False
    cur.execute("ALTER TABLE `user` " + ", ".join(adds))
    return True


def _migrate_message_source_score_normalize(cur, db: str) -> bool:
    """模块二 AI 助手数据迁移（幂等）：存量 message_source.score 从「原始 RRF 融合分」归一化到展示口径。

    旧版落库的是原始 RRF 分（≈1/(60+rank)，双路 top1 最大约 0.033），前端 ×100 渲染成 1%-3% 短条。
    展示口径 = 相对理论峰值：score × (rrf_k+1)/2（rrf_k=60 → ×30.5），与 retriever 置信度同公式。
    阈值 <0.05：旧原始分最大 0.033；新写入的展示分最小 0.05（展开块下限）、真实命中 ≥0.28，
    故该条件只会命中旧数据，重跑天然幂等、不会二次放大新分。
    """
    factor = (get_settings().rag_rrf_k + 1) / 2.0
    cur.execute(
        "UPDATE message_source SET score = LEAST(1.0, ROUND(score * %s, 4)) "
        "WHERE score IS NOT NULL AND score > 0 AND score < 0.05",
        (factor,),
    )
    return cur.rowcount > 0


def main() -> None:
    user, pw, host, port, db = parse_db_url(get_settings().database_url)
    settings = get_settings()

    # 1) 建库（server 层连接）
    conn = pymysql.connect(host=host, port=port, user=user, password=pw, charset="utf8mb4", autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        print(f"[OK] 数据库 {db} 就绪")
    finally:
        conn.close()

    # 2) 执行 schema.sql（db 层连接，逐条执行）
    conn = pymysql.connect(
        host=host, port=port, user=user, password=pw, charset="utf8mb4", database=db, autocommit=True
    )
    try:
        schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        sql = schema_path.read_text(encoding="utf-8")
        stmts = [s for s in sql.split(";") if s.strip()]
        n = 0
        with conn.cursor() as cur:
            for raw in stmts:
                # 剥离每条语句内的注释行（注释与 CREATE 之间无分号，会粘连在同一块，不能整块按 -- 判跳过）
                lines = [l for l in raw.splitlines() if not l.strip().startswith("--")]
                stmt = "\n".join(lines).strip()
                if not stmt:
                    continue
                head = stmt.upper()
                if head.startswith("CREATE DATABASE") or head.startswith("USE "):
                    continue
                cur.execute(stmt)
                n += 1
        print(f"[OK] 建表语句执行 {n} 条（15 张表）")

        # 2.5) E02 重写增强迁移（幂等）：旧库补齐 rewrite_of/rewrite_feedback/rewrite_pending
        with conn.cursor() as cur:
            if _migrate_question_rewrite(cur, db):
                print("[OK] question 表迁移：新增 rewrite_of/rewrite_feedback/rewrite_pending")

        # 2.6) E03 组卷迁移（幂等）：exam_paper 补齐 gen_mode/status 列
        with conn.cursor() as cur:
            if _migrate_exam_paper(cur, db):
                print("[OK] exam_paper 表迁移：新增 gen_mode/status 列")

        # 2.7) E04/E05 考试迁移（幂等）：exam_record 补 state/cheat_count/submit_reason，
        #      exam_answer 放宽长度 + 补唯一键
        with conn.cursor() as cur:
            if _migrate_exam_record(cur, db):
                print("[OK] exam_record/exam_answer 表迁移：E04/E05 字段补齐")

        # 2.8) 模块二 AI 助手迁移（幂等）：message 表补 feedback 列（A07 反馈）
        with conn.cursor() as cur:
            if _migrate_ai_chat(cur, db):
                print("[OK] message 表迁移：新增 feedback 列（A07 反馈）")

        # 2.9) 模块二 AI 助手迁移（幂等）：message_source 补 doc_id/article_no 列（历史引用可点击）
        with conn.cursor() as cur:
            if _migrate_message_source_source_loc(cur, db):
                print("[OK] message_source 表迁移：新增 doc_id/article_no 列（历史引用可点击查看原文）")

        # 2.10) 模块二 AI 助手数据迁移（幂等）：存量 message_source.score 归一化到展示口径
        with conn.cursor() as cur:
            if _migrate_message_source_score_normalize(cur, db):
                print("[OK] message_source 数据迁移：存量相关度分归一化到展示口径")

        # 2.11) 个人中心迁移（幂等）：user 表补 email/avatar 列
        with conn.cursor() as cur:
            if _migrate_user_profile(cur, db):
                print("[OK] user 表迁移：新增 email/avatar 列（个人中心）")

        # 3) 初始化角色（幂等）
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO role (id, code, name, description) VALUES (%s,%s,%s,%s),(%s,%s,%s,%s),(%s,%s,%s,%s)",
                (*ROLES[0], *ROLES[1], *ROLES[2]),
            )
        print("[OK] 角色 3 行就绪（EMPLOYEE/SAFETY/ADMIN）")

        # 4) 初始化管理员（幂等）
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM `user` WHERE username=%s", (settings.admin_username,))
            exists = cur.fetchone()[0]
            if not exists:
                cur.execute(
                    "INSERT INTO `user` (username, password, name, role_id, status) VALUES (%s,%s,%s,%s,1)",
                    (settings.admin_username, hash_password(settings.admin_password), "系统管理员", 3),
                )
                print(f"[OK] 管理员 {settings.admin_username} 创建")
            else:
                print(f"[OK] 管理员 {settings.admin_username} 已存在，跳过")
    finally:
        conn.close()

    print("\n建库完成。自检：\n  mysql -u root -p -e \"USE shudao; SELECT COUNT(*) FROM role; SELECT COUNT(*) FROM question;\"")


if __name__ == "__main__":
    main()
