-- ============================================================================
-- 蜀道安全助手 建库脚本（对齐 docs/DATABASE.md §9）
-- 目标：MySQL 8.x（InnoDB，utf8mb4_unicode_ci）
-- 说明：全部逻辑外键 + 索引，无物理外键；统一主键 id bigint 自增。
--       `user` 为 MySQL 保留字，统一加反引号。
-- 执行：cd shudao/backend && python scripts/init_db.py（脚本自动建库并逐条执行本文件）
-- ============================================================================

CREATE DATABASE IF NOT EXISTS shudao DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE shudao;

-- 角色表
CREATE TABLE IF NOT EXISTS role (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  code        VARCHAR(32)  NOT NULL,
  name        VARCHAR(32)  NOT NULL,
  description VARCHAR(255) NULL,
  create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_code (code)
) ENGINE = InnoDB;

-- 用户表
CREATE TABLE IF NOT EXISTS `user` (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  username     VARCHAR(64)  NOT NULL,
  password     VARCHAR(128) NOT NULL,
  name         VARCHAR(64)  NOT NULL,
  role_id      BIGINT       NOT NULL,
  phone        VARCHAR(20)  NULL,
  status       TINYINT      NOT NULL DEFAULT 1,
  created_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_username (username),
  KEY idx_role (role_id)
) ENGINE = InnoDB;

-- 隐患表
CREATE TABLE IF NOT EXISTS hazard (
  id                    BIGINT AUTO_INCREMENT PRIMARY KEY,
  hazard_no             VARCHAR(32)  NOT NULL,
  title                 VARCHAR(128) NOT NULL,
  description           TEXT         NOT NULL,
  location              VARCHAR(128) NOT NULL,
  level                 VARCHAR(16)  NOT NULL,
  type                  VARCHAR(32)  NOT NULL,
  status                VARCHAR(16)  NOT NULL DEFAULT 'WAIT_PROCESS',
  creator_id            BIGINT       NOT NULL,
  handler_id            BIGINT       NULL,
  deadline              DATETIME     NULL,
  rectification_measure TEXT         NULL,
  rectification_images  TEXT         NULL,
  reject_reason         VARCHAR(255) NULL,
  risk_report           JSON         NULL,
  create_time           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_hazard_no (hazard_no),
  KEY idx_status (status),
  KEY idx_level (level),
  KEY idx_creator (creator_id),
  KEY idx_handler (handler_id),
  KEY idx_create_time (create_time)
) ENGINE = InnoDB;

-- 隐患图片表
CREATE TABLE IF NOT EXISTS hazard_image (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  hazard_id   BIGINT       NOT NULL,
  image_url   VARCHAR(255) NOT NULL,
  uploader_id BIGINT       NOT NULL,
  create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_hazard (hazard_id)
) ENGINE = InnoDB;

-- 隐患处理记录表
CREATE TABLE IF NOT EXISTS hazard_log (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  hazard_id   BIGINT       NOT NULL,
  operator_id BIGINT       NOT NULL,
  operation   VARCHAR(64)  NOT NULL,
  old_status  VARCHAR(16)  NULL,
  new_status  VARCHAR(16)  NULL,
  remark      VARCHAR(255) NULL,
  create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_hazard (hazard_id),
  KEY idx_operator (operator_id)
) ENGINE = InnoDB;

-- 会话表
CREATE TABLE IF NOT EXISTS conversation (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id      BIGINT       NOT NULL,
  title        VARCHAR(128) NOT NULL,
  created_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_user (user_id),
  KEY idx_updated (updated_time)
) ENGINE = InnoDB;

-- 消息表
CREATE TABLE IF NOT EXISTS message (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  conversation_id BIGINT       NOT NULL,
  role            VARCHAR(16)  NOT NULL,
  content         MEDIUMTEXT   NOT NULL,
  token_count     INT          NOT NULL DEFAULT 0,
  status          VARCHAR(16)  NOT NULL DEFAULT 'SUCCESS',
  feedback        TINYINT      NULL COMMENT 'A07 反馈：1=有用 -1=没用 0=清除 NULL=未反馈',
  create_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_conversation (conversation_id)
) ENGINE = InnoDB;

-- 回答引用来源表
CREATE TABLE IF NOT EXISTS message_source (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  message_id    BIGINT       NOT NULL,
  document_id   BIGINT       NOT NULL,
  chunk_id      BIGINT       NOT NULL,
  document_name VARCHAR(255) NOT NULL,
  chapter       VARCHAR(128) NULL,
  content       TEXT         NOT NULL,
  score         DECIMAL(6,4) NULL,
  KEY idx_message (message_id)
) ENGINE = InnoDB;

-- 知识库文档表
CREATE TABLE IF NOT EXISTS knowledge_document (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(255) NOT NULL,
  type        VARCHAR(16)  NOT NULL,
  path        VARCHAR(255) NOT NULL,
  status      VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
  chunk_count INT          NOT NULL DEFAULT 0,
  uploader_id BIGINT       NOT NULL,
  create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_status (status)
) ENGINE = InnoDB;

-- 知识切片索引表
CREATE TABLE IF NOT EXISTS knowledge_chunk (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  document_id BIGINT       NOT NULL,
  content     TEXT         NOT NULL,
  chapter     VARCHAR(128) NULL,
  page_no     INT          NULL,
  seq         INT          NOT NULL,
  vector_id   VARCHAR(64)  NOT NULL,
  create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_document (document_id),
  UNIQUE KEY uk_vector (vector_id)
) ENGINE = InnoDB;

-- 题库表（对齐 PRD §7：batch_id/sources/source_law_title/source_article_no/reviewer/review_note/interference_verified）
CREATE TABLE IF NOT EXISTS question (
  id                    BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_id              VARCHAR(64)  NULL,
  type                  VARCHAR(16)  NOT NULL,
  content               TEXT         NOT NULL,
  options               JSON         NULL,
  answer                VARCHAR(64)  NOT NULL,
  analysis              TEXT         NULL,
  knowledge_point       VARCHAR(128) NOT NULL,
  difficulty            VARCHAR(16)  NOT NULL,
  source                VARCHAR(16)  NOT NULL DEFAULT 'manual',
  sources               JSON         NULL,
  source_law_title      VARCHAR(255) NULL,
  source_article_no     VARCHAR(32)  NULL,
  status                VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
  reviewer              BIGINT       NULL,
  review_note           VARCHAR(255) NULL,
  interference_verified TINYINT      NOT NULL DEFAULT 0,
  rewrite_of            BIGINT       NULL,
  rewrite_feedback      VARCHAR(255) NULL,
  -- 生成列：仅当该行是「待审核(PENDING)的重写题」时 = 原题 id，其余为 NULL。
  -- 唯一键 uk_rewrite_pending 保证同一原题至多一条待审重写（双击/并发防重）。
  rewrite_pending       BIGINT       GENERATED ALWAYS AS (IF(rewrite_of IS NULL, NULL, IF(status = 'PENDING', rewrite_of, NULL))) STORED,
  create_time           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_type (type),
  KEY idx_knowledge (knowledge_point),
  KEY idx_difficulty (difficulty),
  KEY idx_status (status),
  KEY idx_batch (batch_id),
  KEY idx_rewrite_of (rewrite_of),
  UNIQUE KEY uk_rewrite_pending (rewrite_pending)
) ENGINE = InnoDB;

-- 试卷表
CREATE TABLE IF NOT EXISTS exam_paper (
  id               BIGINT AUTO_INCREMENT PRIMARY KEY,
  name             VARCHAR(128) NOT NULL,
  total_score      INT          NOT NULL DEFAULT 100,
  pass_score       INT          NOT NULL DEFAULT 60,
  duration         INT          NOT NULL,
  question_count   INT          NOT NULL,
  difficulty_ratio JSON         NULL,
  gen_mode         VARCHAR(8)   NOT NULL DEFAULT 'manual',
  status           VARCHAR(16)  NOT NULL DEFAULT 'DRAFT',
  creator_id       BIGINT       NOT NULL,
  create_time      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_status (status)
) ENGINE = InnoDB;

-- 试卷-题目关联表
CREATE TABLE IF NOT EXISTS exam_paper_question (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  paper_id    BIGINT NOT NULL,
  question_id BIGINT NOT NULL,
  score       INT    NOT NULL,
  seq         INT    NOT NULL,
  KEY idx_paper (paper_id)
) ENGINE = InnoDB;

-- 考试记录表
CREATE TABLE IF NOT EXISTS exam_record (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  paper_id      BIGINT       NOT NULL,
  user_id       BIGINT       NOT NULL,
  score         INT          NOT NULL DEFAULT 0,
  status        VARCHAR(16)  NOT NULL DEFAULT '',
  state         VARCHAR(16)  NOT NULL DEFAULT 'ONGOING',
  cheat_count   INT          NOT NULL DEFAULT 0,
  submit_reason VARCHAR(16)  NULL,
  start_time    DATETIME     NOT NULL,
  end_time      DATETIME     NULL,
  -- 部分唯一：仅 ONGOING 记录参与唯一（防同用户同试卷重复开考）；SUBMITTED 置 NULL 不参与唯一 → 允许重考/多次交卷历史
  ongoing_key   VARCHAR(40)  GENERATED ALWAYS AS (IF(state = 'ONGOING', CONCAT(user_id, '-', paper_id), NULL)) STORED,
  KEY idx_user (user_id),
  KEY idx_paper (paper_id),
  UNIQUE KEY uk_user_paper_ongoing (ongoing_key)
) ENGINE = InnoDB;

-- 答题明细表
CREATE TABLE IF NOT EXISTS exam_answer (
  id             BIGINT AUTO_INCREMENT PRIMARY KEY,
  record_id      BIGINT       NOT NULL,
  question_id    BIGINT       NOT NULL,
  user_answer    VARCHAR(255) NOT NULL,
  correct_answer VARCHAR(255) NOT NULL,
  is_correct     TINYINT      NOT NULL,
  score          INT          NOT NULL,
  KEY idx_record (record_id),
  UNIQUE KEY uk_record_question (record_id, question_id)
) ENGINE = InnoDB;
