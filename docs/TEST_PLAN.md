# 蜀道安全助手 · 测试方案

> 版本：v1.0 · 日期：2026-08-13 · 适用交付：模块一 隐患安全管理（H01-H03）· 模块二 AI 智能助手（M1-M5）· 模块三 考试工坊（E01-E05）· 前端「蜀道 · 青石黛」视觉重设计回归
>
> 真源约定：以 `docs/PRD.md`（范围收敛）、`docs/ARCHITECTURE.md`、`backend/database/schema.sql`（建表真源）、`backend/app/core/config.py` + `backend/app/rag/rag_config.py`（参数真源）为准；`docs/DATABASE.md §9` 已过时，勿作为建表断言依据。

## 0.1 本方案是什么

一份可直接执行、可进 CI、可作验收交付的完整测试方案。它由一次「盘点 → 分章起草 → 完整性评审」流程产出：

- **盘点**核实了后端全部 7 个 router 的接口契约（方法/路径/鉴权/特殊点）、后端可测逻辑单元、前端可测面、需求文档与既有测试约定，并将约 30 项实现事实（SSE 事件序、视觉 290s 超时、唯一约束、工具链缺失等）写入方案作为断言依据。
- **完整性评审**对照任务书 / PRD / 安全约束共找到 **12 项缺口**，本方案已将全部缺口在正文中修订落实（见附录 A 修订记录），保证「计划写得出来，也执行得了」。

## 0.2 关键结论摘要

- **现状**：后端有 4 个 httpx 直连 8000 端口的手工 E2E 脚本（`test_exam_e2e` / `test_hazard_e2e` / `test_ai_module` / `test_bugfix`），无 pytest 工程、无覆盖率载体、无 CI；前端无任何测试工具链（无 vitest / playwright）。工具链需按各章补装。
- **测试级别**：单元（pytest/vitest 纯函数 + 状态机）→ 集成（mock 单例 + 真实 MySQL 并发专项）→ 端到端（迁移并隔离化既有脚本）→ 系统验收 → 安全 / 性能 / 视觉回归。
- **AI 与外部依赖策略**：输入可构造、输出可由代码校验的分支一律 mock；只有「输出质量本身」（检索召回、识别准确性、题面质量）必须真实调用。真实调用用例打 `@real_llm` / `@ai` 标记，默认跳过、验收时单跑。
- **已核实的实现事实（测试须以此为准）**：SSE `stream_qa` 当前只发 `meta→delta*→done`，**未发 60s ping 帧**；服务层未捕获异常返回 FastAPI 默认 500 而非 `{code,message,data}`；Redis 仅配置未使用；`/ai/batches` 通过率口径 `approved/(approved+rejected)`。
- **验收口径**：以 PRD 收敛范围为准；任务书与 PRD 冲突处（如性能并发 ≥200 vs PRD §6.1 ≥50）在测试报告中显式标注取舍。

## 0.3 章节结构

1. 第一章 总体测试策略与测试管理（范围 / 级别 / 环境 / 需求追踪矩阵 / 缺陷 / 覆盖率 / 排期 / 交付物）
2. 第二章 后端测试方案（单元 + API/E2E）
3. 第三章 前端测试方案（单元 + E2E + 视觉回归）
4. 第四章 AI 模块专项测试方案（视觉识别 / RAG / LLM 出题）
5. 第五章 安全测试 · 性能测试 · 手工验收（UAT）
6. 附录 A 完整性评审缺口与修订记录

## 0.4 用例编号规则（全案统一）

`<段>-<功能序号>-<流水号>`：**B-** 基础支撑、**C-** AI 助手、**D-** 隐患、**E-** 考试工坊、**F-** 前端。各章测试用例表内另用章内自足编号（后端 A1/E1/P1/R1/G1/C1/H1，前端 E2E-A1/B1/C1/D1，安全 S-01…，视觉 V-01…），二者结合即唯一可回溯。

---

---

# 第一章 总体测试策略与测试管理

> 本章为《蜀道安全助手测试方案》总纲，定义三大模块与前端重设计的测试目标、测试级别与策略、环境与数据、需求追踪矩阵、缺陷与回归管理、覆盖率目标、实施排期与交付物。各模块测试细节见后续章节（用例编号遵循本章约定的 B-/C-/D-/E-/F- 编号规则）。

---

## 1. 测试目标与范围

### 1.1 测试目标

1. 验证《PRD.md v1.0.1》三大模块本期范围的功能正确性、数据一致性与权限安全，为验收提供可执行、可复现的证据。
2. 补齐当前测试空白：现存 4 个 backend/scripts 手工脚本（httpx 直连 8000 + 真 MySQL + 真 LLM/视觉 API）不可自动重复、无隔离、无 CI；后端单测/前端单测/CI/压测/覆盖率全部缺失。本方案将其重构为「pytest 单测+集成 + 隔离化 API e2e + vitest 前端单测 + 系统验收 + 性能压测 + CI」的完整闭环。
3. 覆盖前端「青石黛」视觉重设计回归（所有 SFC 的 `<style scoped>` 改为 CSS 变量、大量 DOM/class 结构重写），防止样式重构引入功能与布局回归。
4. 建立需求→用例→缺陷→报告的可追踪基线，满足任务书交付物要求（后端单测覆盖率≥60%、前端核心组件单元测试、CI 流水线、接口文档对齐）。

### 1.2 测试范围（本期验收边界）

**纳入本期验收的功能（以 PRD §1.3 收敛范围为准，任务书全量口径与 PRD 冲突处以 PRD 为准）：**

| 模块 | 功能代号 | 范围说明 |
|---|---|---|
| 基础支撑 | B01 登录注册+JWT | 密码 bcrypt(cost=12)、Token HS256/120min、未登录 401、注册强制 EMPLOYEE |
| 基础支撑 | B02 角色权限 | admin 全通、SAFETY/ADMIN 管理接口、员工禁管理接口 403、禁用账号 401 |
| 基础支撑 | B03 文件上传 | jpg/png/jpeg 白名单 + MIME 双校验、≤5MB(默认)、图片多图≤9 张 |
| 模块一 隐患 | H01 上报 | 文字+图片+等级+可选位置、HZ+日期+序号唯一编号、初始 WAIT_PROCESS |
| 模块一 隐患 | H02 列表 | 状态/等级/类型/关键字/时间区间筛选、分页、sort/order 排序 |
| 模块一 隐患 | H03 详情与闭环 | 时间线留痕、管理员闭环 WAIT_PROCESS→FINISHED、重复闭环 400、他人资源 404 |
| 模块二 AI 助手 | M1 智能问答（A01） | RAG 混合检索+RRF+重排+生成、来源引用、拒答话术、≥5 轮多轮、敏感词 400 |
| 模块二 AI 助手 | M2 会话管理（A02） | 新建/列表（按更新时间倒序）/重命名/删除级联、他人资源 404 掩码 |
| 模块二 AI 助手 | M3 SSE 流式（A03） | 事件序 meta→delta*→done、断线不丢、synthetic 标识；60s ping 心跳（已核实当前实现未发 ping 帧，验收口径以实际行为为准，见第四章 §4.3.7） |
| 模块二 AI 助手 | M4 溯源与原文（A06/A07） | /ai/source 引用列表、/ai/article 原文父块、引用落库一致 |
| 模块二 AI 助手 | M5 反馈与快捷提问（A04/A05） | 反馈幂等 [-1,0,1]、快捷提问列表（A04 任务书原 P2，已实现并纳入） |
| 模块三 考试 | E01 题库 CRUD | 四题型建改删、解析必填、编辑禁改 type、筛选+分页 |
| 模块三 考试 | E02 AI 出题 | ≥5 题/批、batch 批次、人工审核流转、通过率≥80%、REJECTED 重写链 |
| 模块三 考试 | E03 试卷生成 | manual/auto 组卷、时长 30/60/90、合格线默认 60、发布锁总分/及格线 |
| 模块三 考试 | E04 在线考试 | 倒计时权威、15s+切题自动保存、刷新恢复、切屏>3 自动交卷、超时自动交卷、进行中脱敏 |
| 模块三 考试 | E05 自动阅卷 | 客观题自动评分、多选全对得分漏选错选 0 分、成绩单含答案+解析+AI 合成标识 |
| 前端 | 青石黛视觉重设计 | 全部 SFC 样式重构回归：登录/隐患/考试/AI 助手关键页布局与交互 |

**本期不纳入验收（P1/P2 项，明确取舍）：** 任务书 H04-H08（派单/整改/验收/统计/消息通知）、E06-E08 明确不在本期；A04/A07 虽为任务书 P2 但已实现并被 test_ai_module 覆盖，纳入 M5/M4。任务书「隐患 8 点、AI 7 点、模块三 8 点全部实现」的验收口径与 PRD 收敛冲突，测试报告需在结论中注明取舍依据。

**本期不单独验收（仅做稳定性回归）：** 性能与安全基线（§2.6/§2.7 作为非功能冒烟执行，不设正式验收门禁，为 RAG 方案 §6.8 指标落地预留载体）。

---

## 2. 测试级别与策略

整体策略：**自底向上分层覆盖 + 风险驱动加权 + 外部依赖可控化**。按「纯函数单测 → 服务/状态机集成 → 接口端到端 → 系统验收 → 非功能」五层推进，并对盘点出的高风险区（SSE 流、E02 LLM 生成、E04 并发/超时、视觉 290s、鉴权掩码矩阵、全局异常缺口）单独设专项。

### 2.1 单元测试（自动化，pytest + vitest）

- **后端纯函数层（零依赖，覆盖主力）**：`grading_service`（canonicalize/grade，含全角归一化、MULTIPLE 去重排序、FILL 分号切分）、`rag/confidence`（normalize_rrf/classify 的 0.30/0.45 边界）、`rag/rewriter`、`rag/sensitive`、`rag/citations`、`ai/llm_client._extract_json`、`ai/vision` 坐标系（_sanitize/_sanitize_detection/_sanitize_bbox/_to_original_bbox/_remap_detections，数学公式逐断言）、`ai/prompts._allocate/build_*`、`ai/doc_extract`、`rag/build` 清洗/解析/引用扫描、`paper_service._even_split/_check_score_config`、`hazard_service._auto_title`、`exam_service._expired/_remaining/_reason`、`schema` 校验器（ExamAnswersIn._dedup、GenRequest._count_at_least_five）、`qa_service._ground/_to_score/_sse`、`gen_service._pick_source/_normalize_sources/_finalize_rewrite`、`router/menu.ts buildMenu`、`utils/format.ts`、`utils/validate.ts`、`api/request.ts cleanParams`。
  - 关键点：`exam_service._expired/_remaining/_reason` 依赖系统时钟，须参数化 `_now` 或 freezegun 注入，并核对 naive 本地时间与 MySQL DATETIME 口径一致。
- **前端纯函数与工具（vitest + jsdom）**：`utils/markdown.ts`（XSS 净化专项：img onerror、`javascript:` URL、事件属性注入）、`utils/sse.ts`（mock fetch+ReadableStream 受控流、`\n\n` 帧拼接、畸形帧/AbortError 容错）、`QuestionFormDialog` 的 buildOptions/buildAnswer/sameArray、`ExamTaking` 的 fillSlotCount 正则/optionValue/切屏去重、`ExamResult` 的 optClass 判定、`MarkdownRenderer` 的净化后上标注入。
- **前端流式状态机**：`store/modules/chat.ts` 四个归一化函数 + sendMessage 全生命周期（meta→delta*→done、rAF 节流 flushText、stopStreaming abort、finally 兜底残留 streaming），需 fake timers + 受控流。

### 2.2 集成测试（自动化，pytest + mock Session / 真实 MySQL 并发）

- **mock 依赖的服务状态机**：exam 状态机（_finalize 条件 UPDATE rowcount 抢评分权、save/switch SELECT..FOR UPDATE 锁序、已交卷幂等）、hazard 编号重试（IntegrityError 回滚重试 5 次）、review 批量预检、gen 逐题校验先全通过再单事务（半批孤儿防护）。
- **真实 MySQL 并发专项（关键，不可 mock 替代）**：并发双交只评一次（分数一致）、同用户名并发注册 400、uk_user_paper_ongoing 唯一约束、uk_rewrite_pending 并发 409、hazard_no 并发撞号重试。MySQL 方言依赖（INSERT..ON DUPLICATE KEY UPDATE）必须在真实库验证。
- **单例与缓存隔离**：`get_embedder/get_reranker/get_retriever` 三单例、`get_settings()`、`load_corpus()/load_sensitive_words()/load_quick_questions()` lru_cache、`_CONV_LOCKS/_LLM_SEMAPHORE` 进程级状态，测试须 mock 单例 + 逐用例清理缓存，防止跨用例串状态。本地模型加载分钟级，禁止在单测中真实加载。

### 2.3 端到端测试（自动化，httpx/pytest 直连 8000 + 前端手动冒烟）

- **重构现有 4 脚本为 pytest 用例**：test_hazard_e2e（H01-H03）、test_ai_module（A01-A07）、test_exam_e2e（38 项 A1-A13）、test_bugfix（19 项回归）。先封装公共基座：统一 httpx 客户端（login/register helper）、种子数据、前缀命名、清理钩子；修复硬编码题库 id（q1-q6 依赖种子，库重置即失效）问题。
- **补齐盘点缺口**：E01 题库 CRUD 独立用例、E02 生成/批次审核/通过率口径/重写链 409、E03 智能组卷（rules/不足提示/时长合格线/草稿期可改 vs 发布禁改）、H02 sort/order 排序、B02 角色矩阵全接口放行矩阵、A03 流中断/重试、A02 更新时间倒序、H01 多图/位置字段。
- **前端端到端**：登录→隐患上报→考试作答→AI 助手主链路手动冒烟 + Playwright 截图对比（视觉重设计回归），SSE 流式渲染、倒计时、防切屏、上传预校验（≤5MB/白名单）、路由守卫 meta.roles 为集成单测重点。

### 2.4 系统验收测试（半自动）

- 以 §5 冒烟集 SMK-01~12 为准入，逐 PRD 验收点执行，输出《验收记录表》：每条给出通过/不通过/阻塞 + 证据（响应/截图/日志/覆盖率）。
- 验收口径以 PRD 收敛范围为准；对任务书与 PRD 冲突项在报告中显式标注取舍。

### 2.5 性能测试（工具：Locust/k6，首轮为压测脚本交付，非正式门禁）

- 依据 RAG 方案 §6.8 指标落地可执行压测：并发≥50 QPS、AI 首字≤3s（SSE 首包）、API P95≤500ms；RAG 评测集（CI 冒烟 200 问+30 拒答，完整回归 3100+多轮 300+出题 620）落地为可运行评测脚本，指标 Recall@5≥0.92/MRR≥0.85/幻觉率≤5%/拒答正确率≥95%。
- 本轮以「工具与脚本交付 + 基线打点」为目标，不设硬性验收门禁（任务书响应≤500ms 与 PRD 指标冲突时按 PRD 打点记录）。

### 2.6 安全测试（自动化 + 专项）

- **越权矩阵**：多角色（EMPLOYEE/SAFETY/ADMIN + 禁用账号）× 全接口，断言 401（无/坏/过期 token、status!=1 即时失效）vs 403（角色不符/禁用登录）vs 404 归属掩码（chat 会话/消息、exam 记录非本人）语义差异。
- **XSS**：renderMarkdown（marked→DOMPurify）净化绕过专项。
- **JWT**：占位 secret 运行时旋转（重启后旧 token 失效）、篡改签名、过期。
- **上传安全**：非法扩展名 400、>5MB 413/400、uuid 文件名 + 按日期子目录防穿越、MIME 白名单双校验。

### 2.7 视觉回归测试（Playwright 截图对比 + 手动基线）

- 青石黛重设计后几乎所有 SFC 重构，组件快照需全量重录基线。策略：纯单元测试无法覆盖视觉，配 Playwright 截图对比（登录页渐变背景、隐患上报、考试作答、AI 助手会话等关键页），无 Playwright 时以「手动回归清单 + 截图存档」兜底，纳入本期交付。

---

## 3. 测试环境与数据

### 3.1 环境拓扑

| 项 | 配置 |
|---|---|
| 后端 | `cd backend && uvicorn app.main:app --reload`，监听 127.0.0.1:8000 |
| 前端 | `cd frontend && npm run dev`，Vite 监听 5173，`/api`、`/uploads` 代理到 8000 |
| 数据库 | MySQL，库 `shudao`（隔离建议 `shudao_test`），驱动 pymysql，DML 全走 SQLAlchemy 参数化 |
| Redis | `redis://127.0.0.1:6379/0` 已在 config.py 配置但当前代码未使用，测试不依赖（如后续启用 E04 会话需重评） |
| 静态上传 | `/uploads` 挂载 `backend/data/uploads`（启动 mkdir，.gitignore 不入库），图片/标注图静态访问 |
| 知识库 | `backend/data/chroma_kb/`（Chroma 向量库）+ crawler_output/（28 部法规 JSON 语料） |

### 3.2 .env 配置要点（backend/.env）

- `DATABASE_URL`：正确密码（密码含特殊字符时 init_db 已用 SQLAlchemy make_url 权威解析）。
- `JWT_SECRET`：占位/空串时运行时生成随机密钥，**进程重启后旧 token 全失效**——长时间会话测试须固定 secret 或测试前重新登录；测试环境提供 `.env.test` 注入固定 secret。
- LLM/VISION 三组 key：任一缺失时——`/ai/generate`、`/ai/rewrite` 502、`/hazards/analyze` 503（不阻断上报）、`/ai/chat` 走拒答/失败降级。测试须有「配置齐全」与「未配置」两档环境，前者验收正向，后者验证降级分支。

### 3.3 测试账号

| 账号 | 角色 | 准备方式 |
|---|---|---|
| admin / Admin@123456 | ADMIN=3 | `scripts/init_db.py` 自动创建（读 config 默认值） |
| test_employee | EMPLOYEE=1 | register 接口自注册 |
| test_safety | SAFETY=2 | register 强制 EMPLOYEE，需种子脚本/管理员建号 |
| test_disabled | 禁用 | 建号后置 status!=1，验证 JWT 即时失效 401 |

> 建议新增 `scripts/seed_test_users.py` 统一幂等准备四类测试账号，供所有 e2e 复用，替代现有脚本零散注册。

### 3.4 测试数据准备（执行顺序）

1. `python scripts/init_db.py` —— 建表（schema.sql 为准，勿照 DATABASE.md §9 旧版断言字段）+ 角色 + admin。
2. `python scripts/seed_demo.py` —— 4 条手工题（单选/多选/判断/填空，幂等）。
3. `python scripts/build_knowledge_base.py` —— 28 部法规清洗 → Chroma 2544 块 + MySQL，作为 RAG 检索与 AI 出题语料（其 JSON 校验必须全绿）。
4. `crawler/` 产出 crawler_output/ 作为 E02 出题语料（law_corpus 索引）。

### 3.5 数据隔离与清理策略

- **单元测试**：mock Session/repository，不落库；纯函数零 IO。
- **集成测试**：mock Session；并发专项用独立测试库 `shudao_test`（环境变量切换 DATABASE_URL），跑完事务回滚或清理。
- **e2e**：独立库 + 前缀命名（test_ 前缀用户名/标题）避免与真实数据混淆；每个脚本 fixture `teardown` 清理自己造的数据（删除 records/papers/hazards 并重置 AUTO_INCREMENT）。禁用对真实库的盲跑。
- **Chroma 隔离**：RAG 质量用例采用「独立 MySQL 测试库 + 真知识库只读复用」组合口径——向量检索走 `backend/data/chroma_kb`（build_knowledge_base 建的 2544 块真实索引，只读不写，验证 RRF/BM25/citations 落库一致性）；不依赖全量索引的用例（拒答/背压/事件序）用小型 Chroma fixture + mock 单例。独立 collection 下 vector_id↔chunk_id 一致性断言须与引用落库的数据准备对齐。
- **既有脚本改造**：统一退出信号整理与断言库（替代 sys.exit(1) 各色打印），封装公共 base（client/种子/清理）。

---

## 4. 需求追踪矩阵

用例编号段约定：**B-** 基础支撑、**C-** AI 助手、**D-** 隐患、**E-** 考试工坊、**F-** 前端（挂靠对应模块）。格式：`<段>-<功能序号>-<流水号>`，如 `D-01-007` 表示隐患 H01 第 7 条用例。模块代号与 PRD 映射如下。

| 模块代号 | 功能 | 用例段 | 关联 PRD | 说明 |
|---|---|---|---|---|
| B01 | 登录注册+JWT | B-01-xxx | B01 | 含并发注册 400、禁用 401 |
| B02 | 角色权限 | B-02-xxx | B02 | 越权矩阵：401/403/404 掩码 |
| B03 | 文件上传 | B-03-xxx | B03 | 白名单/大小/防穿越/多图≤9 |
| H01 | 隐患上报 | D-01-xxx | H01 | 编号/状态/位置/多图 |
| H02 | 隐患列表 | D-02-xxx | H02 | 筛选/分页/排序 |
| H03 | 详情与闭环 | D-03-xxx | H03 | 时间线/留痕/重复 400 |
| M1 | 智能问答 | C-01-xxx | A01 | 拒答不调 LLM、多轮指代、敏感词 400 |
| M2 | 会话管理 | C-02-xxx | A02 | 倒序列表、级联删除、404 掩码 |
| M3 | SSE 流式 | C-03-xxx | A03 | 事件序/心跳/断线/流中断 |
| M4 | 溯源与原文 | C-04-xxx | A06/A07 | source/article 一致 |
| M5 | 反馈与快捷提问 | C-05-xxx | A04/A05 | 反馈幂等 |
| E01 | 题库 CRUD | E-01-xxx | E01 | 四题型/编辑禁改 type/筛选 |
| E02 | AI 出题 | E-02-xxx | E02 | 批次/审核/通过率/重写链 409 |
| E03 | 试卷生成 | E-03-xxx | E03 | manual/auto/时长/发布锁 |
| E04 | 在线考试 | E-04-xxx | E04 | 倒计时/保存/恢复/切屏/超时/脱敏 |
| E05 | 自动阅卷 | E-05-xxx | E05 | 归一化/多选 0 分/成绩单/并发双交 |
| 横切 | 全局异常/健康检查/契约 | B-00-xxx / F-00-xxx | — | 500 缺口、{code,message,data} 契约、常量对齐 |

> 契约管理：CHEAT_LIMIT=3、AUTOSAVE_INTERVAL=15、图片 5MB/9 张、503 视觉降级码、code!==200 判失败等常量与后端对齐且分散前端多处，测试把常量抽为共享导出并与后端契约绑定（接口文档 API.md 缺失，本方案自建接口清单并随需求追踪矩阵维护）。

---

## 5. 缺陷管理与回归策略

### 5.1 缺陷级别

| 级别 | 定义 | 处理时限 | 示例 |
|---|---|---|---|
| P0 | 阻断发布/安全漏洞/数据错误/全量越权 | 立即 | 任意角色越权、JWT 可离线伪造、判分错误致成绩错误 |
| P1 | 主要功能缺陷，无绕行方案 | 当迭代内 | 在线考试无法交卷、AI 问答拒答误报 |
| P2 | 一般功能/边界缺陷 | 下一迭代 | 分页上限未生效、时间线顺序异常 |
| P3 | UI 文案/建议性 | 可选 | 文案错别字、样式微调 |

### 5.2 处理流程

提交（含前置条件、复现步骤、预期/实际、请求/响应、日志/截图）→ 测试组长评审定级 → 指派修复 → 开发自测 → 测试回归验证（原用例 + 关联用例组）→ 关闭。关闭条件：修复后对应用例通过且不引入关联回归；P0/P1 未关闭前不允许发布。

### 5.3 回归策略

- **回归基线**：每次迭代末执行冒烟集 SMK-01~12（准入/回归入口）全量通过。
- **定向回归**：缺陷修复只回归所属用例组 + 交互模块矩阵行（如考后改题需回归判分快照 E-05、判分 E-04/E-05）；全局改动（异常处理、鉴权、CORS）回归 B-/C-/D-/E- 全段。
- **历史回归资产**：test_bugfix.py 19 个 bug 全部纳入回归基线，防止删卷/删题保护、发布锁、判分快照、及格线>总分、并发注册、禁用 JWT、分页上限、全角归一化等历史问题复发。
- **前端回归**：视觉重设计改样式的 SFC 走 Playwright 截图对比基线；逻辑改动走组件单测。

---

## 6. 覆盖率目标

### 6.1 目标

| 层 | 度量 | 目标 | 说明 |
|---|---|---|---|
| 后端纯函数层 | 语句/分支 | ≥90% / ≥85% | grading/confidence/rewriter/vision 坐标/prompts/schema 校验/build 层，零依赖低成本，设高目标 |
| 后端服务层 | 语句 | ≥70% | exam/hazard/review/gen/qa/auth 服务；状态机/并发/超时/降级关键分支逐条断言 |
| 后端全局（任务书§4.5） | 语句 | **≥60%** | pytest-cov 度量；声明排除 scripts/、lifespan 预热、main 挂载等非可测分支，避免分母失真 |
| 前端核心组件与纯函数 | 语句 | **≥60%** | chat store 流式状态机、utils/*、ExamTaking、路由守卫、QuestionFormDialog 为必测对象 |
| 前端纯工具函数 | 语句 | ≥90% | format/validate/markdown/sse 等 |
| 接口覆盖 | 接口×分支 | 100% 接口至少 1 条 2xx | 自建接口清单内全部接口；鉴权/越权/参数校验分支全覆盖 |
| AI/外部依赖降级 | 分支 | **100%** | LLM/Vision 未配置/失败/超时→502/503/拒答分支以 mock 注入固定错误逐条断言 |

### 6.2 AI 与外部依赖的覆盖计法（明确口径）

- **降级路径计覆盖**：以 mock 注入外部依赖错误，使服务层 502/503/拒答/重试分支真实执行，计入语句与分支覆盖。
- **正向真实调用不计覆盖**：真 LLM/真视觉的验收用例只做功能验证（每次消耗费用），不纳入覆盖率统计。
- **双重证据原则**：每个外部依赖接口同时具备「mock 单元/集成用例（计覆盖）」+「真实 API 冒烟用例（验收）」两条证据链。

### 6.3 覆盖盲区声明

RRF 融合数学与 `top_vec_sim<0.75` 拒答判定内联在 `HybridRetriever.search` / `qa_service.stream_qa` 中（min-max 与相对峰值两套归一化并存），未抽纯函数，只能经 mock 组件做集成覆盖——作为已知技术债记录，建议后续抽出 `rag/score` 纯函数后补单测。

---

## 7. 实施排期与任务分工

> 里程碑依赖：M0 基建 → M1/M3/M4 并行（纯函数、API e2e、前端相对独立）→ M2 依赖 M1（复用判分/归一化纯函数）→ M5 依赖 M3/M4 → M6 收口。

| 里程碑 | 任务清单 | 产出 | 依赖 | 周期 |
|---|---|---|---|---|
| **M0 测试基建** | ① backend 补 pytest/pytest-cov/conftest/fixtures；② frontend 补 vitest+@vue/test-utils+jsdom+happy-dom+setupFiles（pinia 激活、localStorage mock、Element Plus stub）；③ 核验 Vite 8.2/TS 6.0 与 vitest/@vitejs/plugin-vue 兼容矩阵；④ CI 骨架（GitHub Actions） | 可运行的测试框架 + 基座 | 无 | 2-3 天 |
| **M1 后端纯函数单测** | 覆盖 §2.1 全部纯函数清单（高并行度）；`_now` 参数化改造 | pytest 用例 + 覆盖率报告 | M0 | 3 天 |
| **M2 服务层单元+并发集成** | exam 状态机/幂等/锁序、hazard 编号重试、review 预检、gen 孤儿防护（mock）；真 MySQL 并发专项（双交/并发注册/唯一约束 409） | 状态机与并发用例 | M0+M1 | 4 天 |
| **M3 API 端到端** | 重构 4 脚本为 pytest 公共基座；补齐 E01/E02/E03/H02/角色矩阵/A03/A02/H01 多图缺口 | 隔离化 e2e 用例库 | M0+种子 | 5 天 |
| **M4 前端测试** | vitest 纯函数/工具/SSE/chat store/核心组件；Playwright 截图基线（青石黛回归）；路由守卫四分支 | 前端单测 + 截图基线 | M0 | 4 天 |
| **M5 系统验收+非功能** | 冒烟集准入执行；性能压测脚本（50QPS/首字≤3s/P95≤500ms）；RAG 评测集脚本；安全/XSS/越权专项 | 验收记录 + 压测/评测脚本 | M3+M4 | 4 天 |
| **M6 CI 收口与交付** | CI 流水线接线、覆盖率门禁、报告归档、接口清单与契约绑定定稿 | 全套交付物 | M1-M5 | 2 天 |

人员分工建议：测试组长（本章方案、矩阵、报告）；后端测试（M1/M2/M3）；前端测试（M4）；验收执行（M5，含开发与产品共同评审）。

---

## 8. 交付物清单

| # | 交付物 | 内容 | 验收口径 |
|---|---|---|---|
| 1 | 测试方案 | 本章总纲 + 各模块章节 | 覆盖三大模块 + 前端回归，含范围取舍声明 |
| 2 | 测试框架与公共基座 | pytest/conftest/fixtures、vitest 配置、httpx 公共客户端、种子/清理脚本、seed_test_users | `pytest` / `npm test` 一键可跑 |
| 3 | 用例库 | 按 B-/C-/D-/E-/F- 编号的用例文档（前置/数据/步骤/预期） | 需求追踪矩阵逐行可回溯 |
| 4 | 缺陷报告 | 级别/状态/复现/证据/统计 | P0/P1 归零方可发布 |
| 5 | 测试报告 | 逐里程碑：通过率、覆盖率、遗留风险、验收记录表、性能基线 | 结论含 PRD/任务书口径取舍说明 |
| 6 | 覆盖率报告 | pytest-cov + vitest coverage | 后端/前端 ≥60%，纯函数层高覆盖 |
| 7 | CI 流水线 | .github/workflows：lint+单测+e2e 冒烟+覆盖率门禁+冒烟集 | 主分支合并门禁 |
| 8 | 接口清单（替代缺失的 API.md） | 全部接口的请求/响应/鉴权/错误码契约 | 作为需求追踪与契约绑定真源 |
| 9 | 性能与 RAG 评测脚本 | Locust/k6 + 评测集 | 打点基线，为 RAG 方案 §6.8 落地 |

---

# 第二章 后端测试方案（单元 + API/E2E）

> 目标：为蜀道安全助手后端（FastAPI + SQLAlchemy(sync) + MySQL/pymysql + JWT/HTTPBearer + bcrypt）建立可自动化、可重复、可进 CI 的测试体系，覆盖「单元纯函数」「服务层状态机/并发（mock Session）」「API 集成 / 真实 E2E」三个层级。任务书要求的「后端单测覆盖率≥60%」需要有 pytest + pytest-cov 这一可执行载体才能落地（当前仓库无任何 pytest 工程，全部为 scripts/ 下 httpx 直连 8000 端口的手工脚本，见第 4 节迁移策略）。
>
> 对齐口径：响应统一 `{code, message, data}`（utils/response.resp）；业务成功 code=200；鉴权 401、越权 403、不存在统一 404 掩码、参数不合法 422/400；角色枚举 RoleId: EMPLOYEE=1 / SAFETY=2 / ADMIN=3。测试库结构一律以 `backend/database/schema.sql` 为准（勿照 docs/DATABASE.md §9 旧版建表 SQL 断言字段）。

---

## 1. 工具链与骨架

### 1.1 依赖与版本

在 `backend/` 新增 `requirements-dev.txt`（运行依赖沿用 `backend/requirements.txt` + 仓库根缺失的 RAG/AI 依赖清单，根 requirements.txt 需另行补回或在本文件显式补齐 langchain/bge/chroma/jieba/rank_bm25 等）：

```
# backend/requirements-dev.txt
pytest>=8
pytest-asyncio>=0.24          # async LLM / SSE 编排测试
pytest-cov>=5                  # 覆盖率（≥60% 验收载体）
httpx>=0.27                    # TestClient 与真实服务双模式共用
freezegun>=1.5                 # exam 超时/切屏等注入时钟（代码无注入式测试时钟）
aiosqlite>=0.20                # 可选：事务回滚模式用内存库替 MySQL（见 1.3）
```

### 1.2 目录结构

```
backend/
  tests/
    conftest.py                 # 公共 fixture：settings 隔离、get_db override、DB 准备/清理、mock 单例
    unit/
      test_grading_service.py
      test_rag_confidence.py    # + rewriter / sensitive / citations
      test_vision_coords.py     # _sanitize/_sanitize_bbox/_to_original_bbox/_remap_detections
      test_llm_client_extract.py
      test_prompts.py           # _allocate / build_*_prompt
      test_build_clean_parser.py # rag/build 清洗/切块/难度/引用扫描
      test_security.py          # bcrypt/JWT
      test_service_pure.py      # question/paper/hazard/exam/gen/qa 纯函数 + schema validator
    integration/
      test_auth_api.py          # TestClient 模式，override DB + mock 外部依赖
      test_exam_state_machine.py# mock Session/rowcount 测并发抢评分权、行锁、幂等
      test_chat_stream.py       # mock retriever/LLM 测 SSE 编排与拒答
    e2e/
      test_auth.py
      test_hazard_e2e.py        # 迁移自 scripts/
      test_exam_e2e.py          # 迁移自 scripts/
      test_ai_module.py         # 迁移自 scripts/
      test_bugfix.py            # 迁移自 scripts/
      conftest.py               # 真实服务 fixture：启动/复用 uvicorn、种子、清理
    perf/
      load_test.py              # 压测：并发 50 QPS / 首包≤3s / P95≤500ms（Locust 或 k6）
      eval_rag.py               # RAG 评测集：冒烟 200+30 / 全量 3100+多轮 300（@smoke_rag 标记）
      calib_refusal.py          # 拒答阈值标定装置（对齐 RAG优化方案 §0.2/§5）
```

### 1.3 两种运行模式与数据库隔离

- **单元层**：零 DB，直接 import 纯函数，秒级。
- **集成层（TestClient 模式）**：`httpx.ASGITransport(app=app)`（**不触发 lifespan**，避免真实加载 bge 本地模型的分钟级预热）或 `with TestClient(app, ...)`，`dependency_overrides[get_db]` 注入测试 Session。**禁止进入 `lifespan_context`**：main.py 的 `get_embedder/get_reranker/get_retriever` 是模块级已导入函数，monkeypatch 服务层单例拦不住预热；确需覆盖预热路径时 `monkeypatch.setattr(app.main, '_warmup_all', ...)` 或直接 mock 三个 `get_*`。conftest 可执行示例：`transport = httpx.ASGITransport(app=app)`；`async with AsyncClient(transport=transport, base_url='http://test') as c: ...`。数据库隔离二选一：
  1. **独立测试库 `shudao_test`**（推荐）：用 `scripts/init_db.py` 的 schema.sql 建库，每用例级用事务回滚（Session 外包一层 BEGIN…ROLLBACK 的 fixture）或 `TRUNCATE` 关键表 + 数据前缀命名（如用户名 `t_<uuid>`），避免跨用例串数据。
  2. **内存/文件 SQLite + aiosqlite**：仅覆盖 repository 层纯 SQL 逻辑，注意 SQLAlchemy MySQL 方言语法（`INSERT..ON DUPLICATE KEY UPDATE`、唯一约束、`SELECT..FOR UPDATE` 行锁）在 SQLite 上行为不一致——涉及唯一约束的并发/幂等语义**必须**真实 MySQL 集成验证（见 1.4）。
- **E2E 层（真实服务模式）**：复用既有 scripts 前置（uvicorn 8000 + 真 MySQL + 可真 LLM/视觉），作为 CI 夜间或带真 API Key 的可选档（fixture 标记 `@pytest.mark.e2e` / `@pytest.mark.real_llm`，无 key 时 skip）。

### 1.4 隔离要点（跨用例防串）

- **进程级单例全部要 mock/清缓存**：`config.get_settings()`、`get_embedder/get_reranker/get_retriever`（本地 bge 模型加载分钟级，单测必须 `monkeypatch` 三个 get_* 单例）、`load_corpus()`、`load_sensitive_words()`、`load_quick_questions()`、`_CONV_LOCKS/_LLM_SEMAPHORE`、`jwt_secret` 占位旋转。
- **时钟注入**：`exam_service/exam_repo` 全程 `datetime.now()`（naive 本地时区），用 freezegun 冻结或把 `_now` 参数化（`_expired/_remaining/_reason` 已是时间依赖纯逻辑，直接注入时钟单测），并核对 naive 与 MySQL DATETIME 口径。
- **路径注入**：quick_questions.json、sensitive_words.txt、law_json_dir、模型绝对路径在 CI/异构机器不可移植，fixture 显式传入。

### 1.5 运行命令

```bash
cd shudao/backend && pip install -r requirements.txt && pip install -r requirements-dev.txt

# 单元 + 集成（无需 DB/外部 API）
python -m pytest tests/unit tests/integration -m "not e2e" -v

# 全量（E2E 需要 8000 端口 + MySQL + 可选真 LLM/视觉）
uvicorn app.main:app --port 8000 &   # 或复用现有脚本前置
python -m pytest tests/ -m "e2e" -v --tb=short

# 覆盖率（≥60% 验收）
python -m pytest tests/unit tests/integration --cov=app --cov-report=term-missing --cov-fail-under=60
```

---

## 2. 单元测试层（纯函数，零依赖）

目标：把 inventory 中已抽出的纯逻辑全部纳入 `tests/unit/`，单测覆盖率至少覆盖这一层；RAG 数学/拒答阈值（RRF、top_vec_sim<0.75）当前内联在重型类中，通过 mock 组件集成覆盖（见 §2.9）。

### 2.1 判分（grading_service）

- `canonicalize(type_, raw)`：None→''；`' Ａ '` 全角→'A'；FILL `'安全第一；预防为主'`→`'安全第一;预防为主'`（**不转大写**）；MULTIPLE `'b, a ,b'`→`'A,B'`（去重排序、顺序无关）；SINGLE/JUDGE 整体 upper。
- `grade(type_, user_raw, correct_raw, full_score)`：全对→`(1, full_score)`，否则 `(0,0)` 无部分分；MULTIPLE 漏选/错选/多选/空答→0；FILL 空数不一致（多填/少填）→0；未作答（None/''）→0。

### 2.2 置信度阈值（rag/confidence）

- `normalize_rrf([])`→`[]`；`normalize_rrf([0.5,0.5])`→`[0.0,0.0]`（hi-lo<1e-9）；`normalize_rrf([1,3])`→`[0.0,1.0]`。
- `classify(conf, 0.30, 0.45)` 边界：**严格小于**——`0.29→refuse`、`0.30→conservative`、`0.44→conservative`、`0.45→full`。
- 拒答判定 `top_vec_sim < 0.75` 内联在 qa_service.stream_qa，集成层 mock retriever 返回不同相似度断言（见 §2.9）。

### 2.3 坐标重映射（ai/vision，核心公式）

- `_to_original_bbox(bbox, W,H,S,x_off,y_off)`：`left=(min(x1,x2)*S-x_off)/W`、`top=(min(y1,y2)*S-y_off)/H`；边界外→钳到 [0,1]；映射后宽/高<0.02→None；手工构造画布几何（如 S=416、已知偏移）验证像素级回算。
- `_sanitize_bbox([0.5,0.5,0.1,0.9])`：左>右自动交换；len!=4→None；宽/高<0.02→None。
- `_sanitize_detection`：type 收敛到 6 候选否则'其他'；level 四档否则 GENERAL；confidence 夹 [0,1] 保留 4 位；'其他'+bbox=None→丢弃。
- `_sanitize`：兼容 detections 数组/裸对象两形状；按 confidence 降序取主检测；最多 4 处。
- `_remap_detections(result, geom)`：顶层 detections/bbox 与 report 内嵌一并校正。

### 2.4 LLM 响应解析容错（ai/llm_client._extract_json）

- 空串→LLMError；`\`\`\`json...\`\`\`` 围栏剥除；顶层非对象→LLMError；`JSONDecodeError`→LLMError（这些是 gen 层重试/502 的前置，分别固定输入验证「不重试/拒绝」语义）。

### 2.5 Prompt 构造（ai/prompts）

- `_allocate(types, count)`：count<1 或空 types→ValueError；count<n 前 count 类各 1 道；base+余数给靠前题型。
- `gen_service._plan_chunks(allocation, chunk_size)`：各轮求和=全局配额、每轮 ≤chunk_size、跨轮只拆同一类型余量（如 [(S,8),(M,8),(J,7),(F,7)]/20→[[8S,8M,4J],[3J,7F]]）；空 allocation→[]。
- `build_*_prompt`：kp/types 空或 count<1→ValueError；mode=conservative→max_tokens 收紧至 300；`_dump_question` 输出题面 JSON 可被 `_extract_json` 回读。

### 2.6 状态机/编号/校验纯逻辑

- `hazard_service._auto_title(description)`：前 20 字 + 超长补'…'。
- `hazard_service.create` 编号重试：`prefix+count+1`（HZ+yyyyMMdd-4 位序号）；唯一键 IntegrityError 回滚重试最多 5 次、第 5 次仍冲突→500（mock Session，注入重复值断言重试计数与最终 500）。
- `exam_service._expired/_remaining/_reason`：`now>=start+duration`→超时；`_remaining` 下限 0；`_reason` 优先级 timeout>cheat_limit>fallback；CHEAT_LIMIT=3 即第 4 次切屏触发（注入时钟）。
- `question_service._validate_answers`：SINGLE 答案须在选项标签；MULTIPLE 每段在标签集；JUDGE 仅 A/B+固定选项；FILL 空必须非空。
- `paper_service._even_split(total, n)`：divmod 余数分摊到前 r 题；`_check_score_config`：pass>total→400。
- `gen_service._pick_source/_normalize_sources/_extract_single_question/_finalize_rewrite`：kp 命中优先、主溯源缺失 insert(0) 置顶、形状非法→_RewriteRetry、JUDGE 强制固定选项、FILL 置空 options。
- `qa_service._ground(text, n)`：空文本→(空,0,0,0.0)；越界 [n] 删除；total==0→0 分；score=round(valid/total,4)；连续空白折叠。`_to_score`：rrf<=0→None；`_estimate_tokens`：max(1,len/1.5)；`_sse`：双换行分帧。
- `schema` validator：`ExamAnswersIn._dedup`（重复 question_id 后者覆盖前者）、`GenRequest._count_bounds`（<gen_min_count=5 或 >gen_max_count=50→ValueError，上下限真源 settings）。

### 2.7 检索组件（无网络可真跑）

- `rag/bm25.BM25Index.search`：jieba 分词、score<=0 提前 break（降序）、access_level 过滤——用 fixture 小语料真跑，断言命中与过滤。
- `rag/build/clean`、`parser`、`ref` 全链路纯函数：`normalize_status`（未知→'已废止'）、`derive_version`（无年份→v1）、`clean_doc`（title/doc_id 非法→ValueError）、`split_sentences`（保留句末标点）、`compute_difficulty`（罚款词/数字单位/分号≥3/引用≥2/长度>300 各 +1，0=easy/1=medium/≥2=hard）、`_split_child_blocks`（100/250 切分、相邻重叠 1 句、子块 id 后缀 `_dup2` 确定性去重）、`ref` 引用扫描（跨法《书名》第 X 条 + 同法裸第 X 条；found=0→rate 1.0；闸门≥0.90）。

### 2.8 安全原语（core/security）

- `hash_password`：cost=12（`bcrypt.gensalt` rounds 断言或校验哈希前缀 `$2b$12$`）；密码>72 字节→HTTPException 400（而非 500）。
- `verify_password`：正确/错误/非法哈希→False 不抛。
- `create_access_token`：payload sub+exp，HS256 可解码；`jwt_secret` 为占位串时运行时旋转，旋转前后 token 相互不认（模拟进程重启）。
- `get_current_user/require_roles`：无 token→401（`_NO_TOKEN_EXC`）、坏 token/过期/用户不存在/status!=1→401（`_CRED_EXC`）；角色不在列表→403。

### 2.9 内联重型逻辑的集成级单测（mock 组件）

- RRF 融合数学与 `top_vec_sim<0.75` 拒答：`HybridRetriever.search` 尚未抽纯函数——用 fixture 构造 mock 向量 topN + BM25 结果，断言 RRF(K=60) Top20、父块聚合 RRF 取 max、reranker Top5、confidence=min(1, top_rrf*(K+1)/2)；`stream_qa` 注入空检索/低相似度，断言固定拒答话术 + synthetic 标记且**不调 LLM**。
- 考试并发语义：mock `_finalize` 条件 UPDATE 的 `rowcount`，`rows=0`→幂等返回成绩单；mock Session 记录 `SELECT..FOR UPDATE` 锁序（记录→明细）防死锁。

---

## 3. API 集成 / E2E 层（按模块用例表）

统一断言：`r.status_code` 与 `body == {code,message,data}` 双查（400/401/403/404/422/500/502/503 均转 `{code,message,data:null}`，服务层未捕获异常按 §3.6 特殊处理）。表内「角色」列：★=全部登录角色、SAFE=SAFETY/ADMIN（_MANAGE）、EMP=仅 EMPLOYEE 可注册。

### 3.1 auth（prefix /api/v1/auth）

| # | 用例 | 角色 | 正常 | 边界/异常 | 断言 |
|---|------|------|------|-----------|------|
| A1 | 注册 | 公开 | 200，role_id=EMPLOYEE | username 2/65 字、password<6、name 空、phone>20 → 422；用户名重复 → 400 | code=200；`data.user.role_id==1` |
| A2 | 登录 | 公开 | 200，access_token+user | **JSON body→422（必须 form-urlencoded）**；错误密码/不存在用户名→401 统一文案 | `code==200`；401 时 `data==null` |
| A3 | /me | ★ | 200 用户信息 | 无 token 401、坏 token 401、过期 401、**禁用账号(status!=1)旧 JWT 立即 401** | 401 均 `WWW-Authenticate: Bearer` |
| A4 | 角色门禁 | — | SAFE 访问 _MANAGE→200 | EMPLOYEE 访问 /questions、/papers、/ai/generate、/hazards/{hid}/close → 403 | 403 `{code,message,data:null}` |

### 3.2 exam E01 题库（prefix /api/v1/questions，SAFE）

| # | 用例 | 正常 | 边界/异常 | 断言 |
|---|------|------|-----------|------|
| E1 | 列表 | type/difficulty/knowledge_point/status/source/batch_id/keyword 组合筛选 + 分页 | **page>100000 或 page_size>100 → 422（防 OFFSET 溢出）** | 筛选计数与服务端分页一致 |
| E2 | 建/改/删 | 手工录入直接 APPROVED；PUT 落 operator_id；DELETE data=null | 答案不在选项 400/422；删被引题目（试卷引用）→ 400 | 删除响应 `data==null` |
| E3 | 题型约束 | 四题型 CRUD | 编辑禁改 type；JUDGE 答案仅 A/B；FILL 选项置空 | — |

### 3.3 paper E03 试卷（SAFE）

| # | 用例 | 正常 | 边界/异常 | 断言 |
|---|------|------|-----------|------|
| P1 | manual/auto 组卷 | 手动仅取 APPROVED；AI 按 rules 抽题 | 及格线>总分→400/422；时长非 30/60/90→422 | 分数配置校验 |
| P2 | 列表/详情 | gen_mode/status/keyword + 分页；详情含题目预览与答案 | 分页上限 422 | — |
| P3 | 更新/删除 | 草稿期改时长/配置 | **已发布锁总分/及格线；已发布或进行中禁改时长→400；已发布禁删** | 状态门禁 400 |

### 3.4 exam_running E04/E05（★）

| # | 用例 | 正常 | 边界/异常 | 断言 |
|---|------|------|-----------|------|
| R1 | /exams/papers | 仅 PUBLISHED、脱敏无题目（**静态路由先于 /{record_id}**） | — | `Cache-Control` 不含 answer/analysis |
| R2 | start | 200 ONGOING + remaining_seconds + deadline | paper_id<1→422；未发布试卷→400；**并发 start 复用进行中记录（uk_user_paper_ongoing）** | 唯一约束并发 200 |
| R3 | save | 增量自动保存幂等 upsert 不增行 | answers>500→422；**重复 question_id 取末值**；已交卷幂等返回成绩单 | exam_answer 行数不变 |
| R4 | switch | cheat_count 服务端 max 合并；>3（第 4 次）自动交卷 reason=cheat_limit | cheat_count 0..100000，越界 422 | 第 4 次 state=SUBMITTED |
| R5 | submit | 自动阅卷成绩单全字段 | **并发双交只评一次、分数一致**；空卷 0 分 FAIL + 未作答占位行 | 条件 UPDATE 原子抢权 |
| R6 | resume/result | 进行中=题目+已存答案；已交卷=成绩单 | 超时懒校验自动交卷 reason=timeout；他人记录 404 掩码、管理员放行；交卷后任意操作幂等 | 404 掩码 vs 403 区分 |
| R7 | 判分口径 | 全对 100 PASS、多选漏选 0 分、答案归一化（小写/乱序/全角分号） | — | 复用 §2.1 断言 |

### 3.5 ai E02 出题 + 审核（SAFE）

| # | 用例 | 正常 | 边界/异常 | 断言 |
|---|------|------|-----------|------|
| G1 | /ai/generate | ≥5 题/次、同 batch_id、sources 溯源一致；上限 50（settings.gen_max_count，validator 双边界） | LLM 未配置/失败→**502**（mock LLM 抛 LLMError）；Pydantic 校验失败自动重生成≤2 次；题量不足重试≤3 次仍败→502；**count>20 分轮生成（每轮 ≤gen_chunk_size=20，各轮独立调用 LLM，合并同 batch_id）**；任一轮不足配额→502 且无部分落库 | 逐题 PENDING + batch_id 一致；30 题分 2 轮仍单批次 |
| G2 | /ai/doc | txt/md/pdf/docx 解析纯文本；文本>5000 截断 truncated=true | **非法扩展名→400；>5MB→413（413 而非 400）** | 不落盘仅回 text |
| G3 | 审核 | APPROVED 入库/REJECTED 驳回落 reviewer/note | source!=ai→400；REJECT 无意见→400；重复修订版→409（uk_rewrite_pending） | batch 任一路失败整批不入库 |
| G4 | rewrite | 驳回题回喂 LLM，**就地替换原题**：内容/选项/答案覆盖、状态回到 PENDING、原批次不变、不新建批次不产生新题 | 仅 REJECTED+source=ai；已通过修订版存在时禁止重写→409；存量待审修订版（旧独立批次遗留）自动顶替为 REJECTED；清 review_note、重置 interference_verified；LLMError→502 | 溯源必须在知识库 |
| G5 | /ai/batches、/ai/batches/{id}、/ai/stats | 批次列表 pass_rate 口径 `approved/(approved+rejected)`、空批次 0.0；批次详情；出题统计 | **通过率分子分母口径与空批次 0.0 断言**；批次间题量一致 | 口径与前端展示一致 |
| G6 | /exams/records | 本人考试记录分页 | 他人记录不出现；分页 total 与本人记录一致 | 仅返回本人数据 |

### 3.6 chat（模块二 AI 助手，★）—— SSE 特殊处理

SSE 断言方式：用 `httpx.AsyncClient.stream()` 或同步 client 以 `event_stream` 逐事件读取；mock 检索层与 LLM（stub `chat_stream` 返回受控增量），**逐事件断言 meta→delta*→done 事件序**，`done` 的 citations/grounding_score/synthetic=true 与 meta 一致；注入断流/慢响应验证 60s ping 保活与「出流后中断→FAILED、首块前可重试 1 次」语义。客户端读流超时须大于服务端 120s 上限（配置项）。

| # | 用例 | 正常 | 边界/异常 | 断言 |
|---|------|------|-----------|------|
| C1 | /ai/chat | 事件序 meta→delta*→done；引用落库 join knowledge_chunk/document 且 chunk_id=vector_id 一致 | **敏感词预检流前同步 400（不进检索/LLM）** | 事件序 + citations 一致 |
| C2 | 拒答 | 检索空/相似度<0.75→固定话术不调 LLM | synthetic 标记 + grounding 为空 | mock retriever 空 |
| C3 | 会话 CRUD | 新建/列表（按更新时间倒序）/重命名 1-64/删除级联清 message+message_source | **他人会话/消息/删除/引用→404 掩码（防枚举）**；title 越界 422 | 级联 count 归零 |
| C4 | 反馈/原文 | feedback Literal[-1,0,1] 单行 UPDATE 幂等 | 非 assistant 消息给反馈→400；/ai/article 缺 doc_id 或 article_no→422；无 DB 归属校验 | 幂等 1→1→0 |
| C5 | 快捷提问 | lifespan 加载列表 | 文件缺失/JSON 非法→[] | 200 数组 |

### 3.7 hazard（模块一隐患，★ / 闭环 SAFE）

| # | 用例 | 正常 | 边界/异常 | 断言 |
|---|------|------|-----------|------|
| H1 | 上传 | 200 返回 /uploads/YYYYMMDD/uuid.jpg | **扩展名+ MIME 双白名单 400；>5MB 400；防路径穿越（uuid 文件名 + 日期子目录）** | URL 前缀 /uploads/ |
| H2 | analyze | 200 type/level/description/reason/confidence/bbox/detections/annotated_url/report | **视觉未配置/失败/超时→503（不阻断后续上报）**；无隐患→detections 空/null 分支 | 503 走前端降级 |
| H3 | 上报 | 编号 HZ+yyyyMMdd-4 位；title 缺省取描述前 20 字 | description 1-2000，空→422；extra 多传字段→422；images≤9 越界 422 | 唯一编号 + 待处理时间线 |
| H4 | 列表 | status/level/type/keyword/start_time/end_time 组合 + 分页 | **sort 非 create_time|level、order 非 asc|desc→422；page>100000 422** | 筛选/排序参数白名单 |
| H5 | 详情/闭环 | 详情含图片+时间线倒序 | 员工闭环→**403**；不存在→404；非 WAIT_PROCESS 重复闭环→**400**；管理员闭环落 CLOSE 时间线留痕 | 状态机 + 越权 403 vs 掩码 404 |

### 3.8 全局与特殊处理

- GET / 健康检查：200 `{status:ok,module}`，无 DB 依赖。
- **全局异常处理缺口（预期行为，写进断言）**：服务层未捕获异常（ValueError/IntegrityError/MySQL 断连/超时）返回 **FastAPI 默认 500 格式而非 `{code,message,data}`**——测试应显式覆盖该分支并标注这是已知缺口（后续应在 main.py 增加 catch-all handler）。
- /uploads 静态挂载：上传后的 URL 可 GET 回读且 Content-Type 正确。
- 分页溢出（三处 `page<=100000`、`page_size<=100`）：统一 422 断言。

---

## 4. 从既有 scripts/ 迁移/扩展为 pytest 用例集的策略

既有 `scripts/test_exam_e2e.py`（38 项 A1-A13）、`test_hazard_e2e.py`（T1-T13）、`test_ai_module.py`（A01-A07 会话+SSE）、`test_bugfix.py`（19 个回归）是**直连 8000 端口 + 真 MySQL + 真 LLM/视觉**的 httpx 脚本，组织方式（`ok()` 断言 + FAILURES 收集 + main() 串行）可直接映射为 pytest：

1. **脚本→E2E 测试类**：每个脚本的 main() 拆分到 `tests/e2e/test_*.py` 的测试类/函数，`ok(name, cond)` 的 FAILURES 列表改成 `assert`（pytest 自动收集 + `-x` 早停）。保留公共基座：`new_client()`→fixture `e2e_client`、`login/register_or_login`→fixture `admin_token/employee_token`、`create_published_paper`→fixture 工厂。
2. **数据隔离改造**：原脚本用时间戳用户名避免撞名、靠 SQL 清理不彻底——pytest 版本用 `t_<uuid>` 前缀命名 + `yield` fixture 的 teardown 清理（DELETE 级联），并收进独立测试库 `shudao_test`（先 `init_db.py` 建库）。
3. **硬编码 id 去硬编码**：`test_exam_e2e` 依赖 q1-q6（含历史重建的 24/23）在库重置后失效——改为每个用例前置通过 `POST /questions` 自建题目并记录 id，不依赖种子。
4. **外部依赖分档标记**：`@pytest.mark.real_llm`（消耗真实 DeepSeek/百炼费用，默认 skip，CI 夜间档运行）、`@pytest.mark.e2e`（需 8000 端口）。无 key 的环境跑 `-m "not real_llm"`。
5. **新增补缺用例**：inventory 中「已实现但无专门用例」的验收点要补：E01 题库四题型建改删与编辑禁改 type、E02 批次审核流转与通过率≥80% 口径、REJECTED 重写链 409、E03 智能组卷 rules 与时长/合格线、H02 sort/order 排序参数、H01 多图（≤9）与位置字段、B02 角色矩阵全量（管理员全放行/员工管理接口 403）、A03 流中断/重试、A02 按更新时间倒序。
6. **性能/非功能从脚本拆出**：SSE 首字延迟、50 QPS 压测、Recall@5≥0.92 等评测放 `tests/perf/` 与独立评测脚本，不进常规 pytest 门禁（异步 + 真模型，另做 CI 夜间任务）。

**风险与对策**：① 视觉/SSE 长超时（analyze 290s、chat 120s）——客户端 timeout 必须大于服务端上限，SSE 用例用受控 mock 流测编排，真 API 用例单独标记；② 依赖库与模型加载慢——单测/集成层全部 mock `get_embedder/get_reranker/get_retriever` 单例，避免每次分钟级加载；③ 版本兼容——Vite 8/TS6 系属前端，后端 pytest 无此问题，但 `pytest-asyncio` 需与 python-jose/bcrypt 共存时注意事件循环作用域（`asyncio_mode=auto` 或显式 `@pytest.mark.asyncio` 指定 loop scope）。

---

# 第三章 前端测试方案（单元 + E2E + 视觉回归）

> 面向目录：`D:\code\2026\7_8月实训\shudao\frontend`。本文为「蜀道安全助手」前端三层测试（单元 + E2E + 视觉回归）的可执行方案，对齐 PRD 三大模块与「青石黛」视觉重设计交付。

## 1. 现状与目标

**现状（已核实）**：`frontend/package.json` 的 scripts 仅 `dev/build/preview`，devDependencies 无 vitest / @vue/test-utils / @playwright/test；`vite.config.ts`（`D:\code\2026\7_8月实训\shudao\frontend\vite.config.ts`）无 `test` 配置；`tsconfig.app.json` 的 types 仅 `["vite/client"]`。即：**前端测试工具链完全缺失，任何组件/状态/工具函数均无自动化覆盖**，与任务书 §4.5「前端核心组件需有单元测试」的要求存在硬缺口。

但可测面已大量存在（盘点已证实）：`utils/`（validate/format/markdown/sse/constants 均含纯逻辑）、`store/`（hazard 跨页会话态、user 登录态、chat 流式状态机、app）、关键组件（QuestionCard 选项/答案归一化、QuestionFormDialog 表单构建、ExamCountdown 计时、HazardImageUpload 上传校验、AiAnalyzePanel 识别面板、CitationPanel、MarkdownRenderer XSS）、路由守卫与 `buildMenu` 角色过滤。**目标：以三层金字塔（单元 → E2E → 视觉回归）补齐，先覆盖纯逻辑与状态机，再覆盖关键业务流，最后以截图对比守护「青石黛」视觉基线。**

## 2. 工具链补装与版本约束

### 2.1 版本矩阵（2026-08 实测，必须先核验再装）

| 依赖 | 约束 | 说明 |
|---|---|---|
| Node | ≥ 20.19（本机 v24.15.0 满足） | Vite 8 硬要求 |
| vite | ^8.2.0（本机 8.2.1） | 底层 bundler 已切 rolldown |
| @vitejs/plugin-vue | ^6.0.8（已装） | 与 Vite 8 配套 |
| **vitest** | **^4.1.1** | **Vitest 4.1.x 是首个完整支持 Vite 8 的版本线；旧 Vitest（3.x）不支持 Vite 8，勿装** |
| @vue/test-utils | ^2.4.6 | Vue 3 官方测试库 |
| jsdom | ^26 | 组件 DOM 环境（若追求速度可换 happy-dom，本方案按任务书要求用 jsdom） |
| @vitest/coverage-v8 | ^4.1.1 | 覆盖率（v8 provider） |
| @playwright/test | ^1.5x | E2E + 视觉回归（Windows 需 `npx playwright install chromium` 下载浏览器） |

安装命令（在 `D:\code\2026\7_8月实训\shudao\frontend` 下执行）：

```bash
npm i -D vitest@^4.1.1 @vue/test-utils@^2.4.6 jsdom@^26 @vitest/coverage-v8@^4.1.1 @playwright/test@^1.5x
npx playwright install chromium
```

### 2.2 package.json scripts（追加）

```json
"scripts": {
  "dev": "vite",
  "build": "vue-tsc -b && vite build",
  "preview": "vite preview",
  "test": "vitest run",
  "test:watch": "vitest",
  "coverage": "vitest run --coverage",
  "e2e": "playwright test --config tests/e2e/playwright.config.ts",
  "visual": "playwright test --config tests/visual/playwright.config.ts",
  "visual:update": "playwright test --config tests/visual/playwright.config.ts --update-snapshots"
}
```

### 2.3 vite.config.ts 追加 test 配置

文件：`D:\code\2026\7_8月实训\shudao\frontend\vite.config.ts`。在文件头加 `/// <reference types="vitest/config" />` 让 `defineConfig` 接受 `test` 键，并追加：

```ts
/// <reference types="vitest/config" />
// ...（保留原有 plugins / resolve.alias / server.proxy / build）

test: {
  environment: 'jsdom',
  globals: true,
  css: false,                       // SFC 样式不注入，避免测试期依赖 CSS 变量
  setupFiles: ['./tests/unit/setup.ts'],
  include: ['tests/unit/**/*.{test,spec}.{ts,tsx}'],
  restoreMocks: true,               // 每个用例自动恢复 vi.mock/vi.spyOn，防跨用例污染
  coverage: {
    provider: 'v8',
    reporter: ['text', 'html', 'json-summary'],
    include: ['src/**/*.{ts,vue}'],
    exclude: [
      'src/main.ts', 'src/App.vue', 'src/components/HelloWorld.vue',
      'src/types/**', 'src/api/**',           // api 层在 store 测试里以 vi.mock 覆盖
    ],
    thresholds: { statements: 60, functions: 60, branches: 50, lines: 60 },
  },
}
```

> 建议：首期（补链后第一轮）阈值为「有且通过」即可（0 → 60% 一次到位太激进，SFC 模板分支多为 JSX-less 难覆盖）；跑通后再按 `coverage report` 实际值上调。任务书对后端是 ≥60%，前端口径以「核心组件 + utils + store 必测面」为准，全量 statements ≥60% 为二期目标。

### 2.4 目录结构（新增）

```
frontend/
  tests/
    unit/                       # vitest + @vue/test-utils + jsdom
      setup.ts                  # 环境装配（见 2.5）
      utils/validate.spec.ts
      utils/format.spec.ts
      utils/markdown.spec.ts    # XSS 用例
      utils/sse.spec.ts         # mock fetch + 受控 ReadableStream
      utils/constants.spec.ts
      store/hazard.spec.ts
      store/user.spec.ts
      store/chat.spec.ts        # fake timers + rAF stub
      store/app.spec.ts
      components/question-card.spec.ts
      components/question-form-dialog.spec.ts
      components/exam-countdown.spec.ts
      components/exam-taking.spec.ts     # fillSlotCount 正则/optionValue/切屏去重（对齐总体章 §2.1）
      components/exam-result.spec.ts     # optClass 判定（全对/错选/漏选）
      components/hazard-image-upload.spec.ts
      components/ai-analyze-panel.spec.ts
      components/citation-panel.spec.ts
      components/markdown-renderer.spec.ts
      router/menu.spec.ts
      router/guard.spec.ts
      request/clean-params.spec.ts
    e2e/                        # Playwright（真后端 127.0.0.1:8000）
      playwright.config.ts
      flows/01-auth-home.spec.ts
      flows/02-hazard-flow.spec.ts
      flows/03-ai-chat.spec.ts
      flows/04-exam-flow.spec.ts
      fixtures/seed.spec-helper.ts   # 公共登录/造数/清理基座
    visual/                     # Playwright 截图对比（青石黛）
      playwright.config.ts
      specs/*.spec.ts
      __snapshots__/            # 基线截图（入库）
    artifacts/                  # 报告/失败截图（.gitignore）
```

### 2.5 tests/unit/setup.ts 要点

```ts
import { config } from '@vue/test-utils'
import { vi } from 'vitest'
// Element Plus 组件全局 stub（不加载真实 EP，提速并避免 jsdom 兼容问题）
config.global.stubs = { 'el-button': true, 'el-input': true, 'el-tag': true, 'el-form': true, 'el-upload': true, 'el-image': true, 'el-progress': true, 'el-icon': true, 'el-checkbox': true, 'el-dialog': true, 'transition': true, 'transition-group': true }
// jsdom 缺失的浏览器 API
Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation((q) => ({ matches: false, media: q, onchange: null, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })) })
global.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} }
// rAF 节流降级为宏任务，配合 vi.useFakeTimers() 可推进（chat store 需要）
vi.stubGlobal('requestAnimationFrame', (cb) => setTimeout(cb, 0))
vi.stubGlobal('cancelAnimationFrame', (id) => clearTimeout(id))
// Pinia 每用例隔离（store 测试文件内 beforeEach(() => setActivePinia(createPinia()))）
```

测试内显式 `import { describe, it, expect, vi, beforeEach } from 'vitest'`，避免改 `tsconfig.app.json` 的 types。

## 3. 单元测试设计（vitest + @vue/test-utils + jsdom）

**隔离铁律**：所有 store 测试 `beforeEach(() => setActivePinia(createPinia()))`；所有 API 调用 `vi.mock('@/api/...')`；跨用例清 `localStorage` 与 pinia 实例，杜绝「hazard 会话态串扰 / chat currentId 残留」造成的假红假绿。

### 3.1 utils 纯函数

| 文件（绝对路径） | 被测 | 用例要点 |
|---|---|---|
| `D:\code\2026\7_8月实训\shudao\frontend\src\utils\validate.ts` | `validateImage` | 扩展名 `(\.jpg|\.jpeg|\.png)$` 白名单（大小写不敏感）；`>5MB` 返回文案；合法文件返回 `null`；空文件名不抛错 |
| `src\utils\format.ts` | `percent` | `0→"0%"`、`0.8→"80%"`、`1→"100%"`、`null/undefined→"-"`、`1.234→"123%"`（round） |
| `src\utils\format.ts` | `formatDateTime/formatDate` | 空值→`'-'`；非法日期（如 `'not-a-date'`）→`'-'`；合法 `dayjs` 格式 `YYYY-MM-DD HH:mm` |
| `src\utils\format.ts` | `formatRelative` | `<1min→刚刚`；`<60min→N 分钟前`；`<24h→N 小时前`；更早→`MM-DD HH:mm`；非法→`'-'` |
| `src\utils\format.ts` | `formatSeconds` | `0→"00:00"`、`65→"01:05"`、`3725→"1:02:05"`、负数→`"00:00"`（clamp） |
| `src\utils\markdown.ts` | `renderMarkdown` | **XSS 必测**：`<img src=x onerror=alert(1)>`、`<a href="javascript:alert(1)">x</a>`、`<script>` 标签被 DOMPurify 剥离；正常 `# 标题`/表格/链接渲染；空串→`''` |
| `src\utils\sse.ts` | `chatSSE` | mock `global.fetch` 返回受控 `ReadableStream`，断言按 `\n\n` 切帧、`event:`/`data:` 解析、`meta→delta→done` 分发序；`ping` 心跳帧与畸形 JSON 帧静默忽略；非 `text/event-stream` 响应与 `HTTP 401` → `onError(message, code)`；`AbortError` 不触发 `onError`；带 token 时请求头注入 `Authorization: Bearer …` |
| `src\utils\constants\hazard.ts` / `question.ts` / `paper.ts` | 等级/状态/类型映射 | `hazardLevelMeta('UNKNOWN')` 兜底 `{tag:'info'}`；`questionTypeLabel('MULTIPLE')→'多选题'`；`difficultyMeta('HARD')→'困难'`；未知值原样兜底不抛错 |

### 3.2 Pinia store

| 文件 | 被测 | 用例要点 |
|---|---|---|
| `src\store\hazard.ts` | 跨页会话态 | `setAnalyzeResult/setAnalyzeStatus` 增改；`deleteAnalyzeResult/deleteAnalyzeStatus` 删；**`pruneAnalyzeState(['u1'])` 清理已删图片孤儿状态（u2 结果/状态被清、u1 保留、未变更时对象引用不变）**；`resetAnalyze` 全清（images/fileMap/results/status/analyzing/aiDown 归零）；**`carryToReport(r, imgs)` → `consumeReportCarry()` 一次性消费（首次取回、第二次返回空 result+[]，防串上报）**；`setAnalyzeFile/getAnalyzeFile/deleteAnalyzeFile` 的 Map 存取 |
| `src\store\user.ts` | 登录态 | `login` 成功后 `localStorage['shudao_token']` 写入 + `isLoggedIn=true` + `roleId`；`fetchMe` 填 user；`logout` 清 token/user/localStorage；`roleId` 在无 user 时 `0` |
| `src\store\modules\chat.ts` | 流式状态机 | `normalizeLiveCitation`：脏数据丢弃（缺 title/chapter→null）、`clickable = docId && articleNo` 齐备才 true；`normalizeStoredSource`：无 `article_no` 一律不可点击；`toUiMessage`：SUCCESS→success、其余→error、assistant 才带 citations；**`sendMessage` 全生命周期（fake timers + rAF stub）：`meta` 更新 conversation_id/首问懒建会话、`delta` 节流累积、`done` 收尾写 answer_id/citations、无 done 提前断流→有内容按 success 空按 error 兜底、`finally` 把残留 streaming 收尾**；`stopStreaming` 后 streaming→error「已停止生成」；`sendMessage` 空文本/流式中直接 return 不发起 |
| `src\store\app.ts` | `toggleCollapse` | `false→true→false` |

### 3.3 关键组件（mount + global.stubs）

| 文件 | 被测 | 用例要点 |
|---|---|---|
| `src\components\hazard\HazardImageUpload.vue` | 上传状态机 | `beforeUpload` 命中 `validateImage` 错误 → `ElMessage.warning` 且不调 `uploadHazardImage`（mock api 断言未调用）；**≥max(9) 张后再选 → 阻断提示「最多上传 N 张」**；`doUpload` 成功 → emit `update:modelValue` 追加 url、fileMap 记录 url→File；`removeAt` 删除 url 同时清 fileMap；503 降级 → `ElMessage.warning('…可跳过…')`；`getFileByUrl` 经 expose 可取回 File |
| `src\components\hazard\AiAnalyzePanel.vue` | 识别面板 | `levelMeta` 兜底（`level_suggest` 非法→`MINOR` info 标签）；`percent(confidence)` 展示；detections 按 `i+1` 单色编号渲染；`actionable` 时点「应用到表单」emit `apply` |
| `src\components\exam\QuestionCard.vue` | 题目渲染 | `optionLetter` 兼容 `A. / A、 / A / A） / A：`；`optionBody` 剥前缀；`answerText` 归一化：**JUDGE `A→'A（正确）'`、`B→'B（错误）'`、MULTIPLE 按逗号切分大写顿号连接、FILL 分号统一**；JUDGE 固定选项 `['A 正确','B 错误']`；sourceLines 溯源行组装（law_title+第X条） |
| `src\components\exam\QuestionFormDialog.vue` | 表单构建 | `buildOptions/buildAnswer` 补字母前缀（A/B/C…）；`optionsValid`（≥2 非空选项）、`answerValid`（按题型校验答案字母合法性，SINGLE 单字母、MULTIPLE 每段在标签集、JUDGE 仅 A/B、FILL 非空）；题型切换清答案；编辑模式 `buildUpdatePayload` 仅提交变更字段；`sameArray` 判定 |
| `src\components\exam\ExamCountdown.vue` | 计时 | **fake timers**：初始 `seconds` 生效、每秒递减、归零 emit `finish` 并停表（不再触发多次）；`props.seconds` watch 变化以服务端校正本地；`warn`（≤warnSeconds）红色预警；`percentage` 环形进度 clamp 0-100 |
| `src\views\exam\ExamTaking.vue` | 作答交互纯函数 | `fillSlotCount` 正则识别（（1）（2）/①②）填空空位；`optionValue` 值映射；切屏去重（cheat_count 只增不重）；dirtySet 仅标记变化题；自动保存节流 |
| `src\views\exam\ExamResult.vue` | 成绩单判定 | `optClass(userOpt, correctOpt)` 全对=ok / 错选=bad / 漏选=missed / 空=空态；JUDGE/MULTIPLE 归一化展示口径与后端一致 |
| `src\components\chat\CitationPanel.vue` | 引用条 | `clickable=false` 时点击不 emit `view`；`score` 钳制 0-100 百分比；无 citations 不渲染 |
| `src\components\chat\MarkdownRenderer.vue` | 净化+上标 | **先净化后追加 `[n]→<sup>`（`\d{1,3}` 受控）**：`<img onerror>` 注入被净化、`[12]` 转上标、`loading` 打字光标渲染 |
| `src\components\chat\ChatInputBar.vue` | 输入条 | 空白 trim 后禁用发送；流式中禁用 |

> **v-html 四消费点 XSS 回归（对齐安全章 S-13/S-14）**：除 `MarkdownRenderer` 外，`QuestionCard`（answerText/解析）、`ExamResult`（答案解析）、`ArticleDialog`（知识库原文全文）三处 `v-html` 消费点各补注入用例——`<img src=x onerror=alert(1)>`、`<a href="javascript:alert(1)">x</a>`、`<script>alert(1)</script>`；断言 DOMPurify 剥离后无存活危险标签/属性，且净化后追加的 `[n]→<sup>` 仅匹配 `\d{1,3}` 不受注入影响。

### 3.4 路由守卫与菜单

| 文件 | 被测 | 用例要点 |
|---|---|---|
| `src\router\menu.ts` | `buildMenu(roleId)` | 纯函数：EMPLOYEE(1) 无「考试工坊·管理」组且空组被剔除；SAFETY(2)/ADMIN(3) 含管理组；默认（无 roles）全可见 |
| `src\router\index.ts` | beforeEach 守卫 | 集成单测（`createRouter` + 内存 history + setActivePinia）：未登录访问 `/hazards` → 重定向 `/login?redirect=/hazards`；已登录访问 `/login` → 跳 `/home`；已登录但无 user（刷新）→ await fetchMe（mock 成功放行 / 失败回登录）；EMPLOYEE 访问 `/exam/questions`（roles [2,3]）→ `ElMessage.warning` + 回 `/home` |

### 3.5 API 层

| 文件 | 被测 | 用例要点 |
|---|---|---|
| `src\api\request.ts` | `cleanParams` / `ApiError` | 过滤 `undefined/null/''`，保留 `0/false`；`request<T>` 在 `code!==200` 抛 `ApiError(code,message)`；`uploadRequest` 原样返回 body 供 503 视觉降级自判（mock axios adapter 断言） |

## 4. E2E 核心业务流（Playwright）

**基建**：真后端（`uvicorn app.main:app`，127.0.0.1:8000，真 MySQL）+ 前端 `vite dev`（proxy 到 8000）。Playwright baseURL = `http://127.0.0.1:5173`。**projects 配置 chromium 为主，另加 firefox/webkit 冒烟档（仅 登录→上报→问答→考试 四条关键流），对齐 PRD §6.3 跨浏览器兼容要求；若本期只验收 Chromium，须在测试报告中显式记录取舍。** 公共基座 `tests/e2e/fixtures/seed.spec-helper.ts` 封装：`loginAs(role)`（admin/safety/employee，按需注册或使用种子账号）、带图上报造数、`cleanup()` 清理测试数据。**AI 依赖的两条流（SSE 问答、视觉识别）提供双档位**：`mock` 档（`page.route` 拦截 `/api/v1/ai/chat` 返回受控 SSE 帧、`/api/v1/hazards/analyze` 返回固定 JSON）供 CI 常态回归；`real` 档（真 LLM/百炼视觉）供冒烟验收，用 `@tag @ai` 区分、默认跳过。

### 4.1 流 A：登录 → 首页 → 隐患上报(带图) → AI 分析 → 列表筛选 → 详情 → 管理员闭环

| # | 步骤 | 断言 |
|---|---|---|
| E2E-A1 | 未登录访问 `/hazards` → 落到 `/login?redirect=/hazards`；登录 admin → 回跳 `/hazards` | URL 含 redirect 并在登录后回跳；首页模块磁贴含「隐患管理/AI 助手/考试中心」且不含管理项给 EMPLOYEE |
| E2E-A2 | 上报页：空描述提交 | 校验拦截（「描述不能为空」类文案），不调 create |
| E2E-A3 | 上传 1 张 jpg（≤5MB）→ 预览缩略图 → 填描述/等级 → 提交 | 列表出现该隐患，编号 `HZ+yyyyMMdd-序号`，状态「待处理」 |
| E2E-A4 | 上传非法文件（.txt）与 >5MB 图片 | beforeUpload 阻断：提示「仅支持 jpg/png/jpeg」/「超过大小上限」，不上传 |
| E2E-A5 | AI 分析页：上传 2 张图 → 顺序识别（mock 档）→ 结果面板 | 逐张 pending→running→done；单色编号列表渲染；`aiDown`（503）时中止后续并提示可跳过 |
| E2E-A6 | 识别结果「应用到表单」→ 跳上报页 | onMounted `consumeReportCarry` 一次性回填描述/等级/图片；再进上报页不残留（防串） |
| E2E-A7 | 列表五维筛选：状态=待处理 + 等级=一般 + 关键字 + 时间区间 | 仅返回匹配记录；URL 参数组装正确（`sort=create_time&order=desc` 默认） |
| E2E-A8 | 详情页：图片缩略图 + 时间线；EMPLLOYEE 无闭环按钮 / admin 有 | 时间线含「创建」记录；canClose 双门控生效 |
| E2E-A9 | admin 一键闭环 → 确认 | 状态变「已闭环」+ 时间线新增闭环留痕；再点提示重复闭环 |

### 4.2 流 B：法规问答（SSE 流式）

| # | 步骤 | 断言 |
|---|---|---|
| E2E-B1 | 进 AI 助手 → 首问「高处作业安全距离是多少」（mock 档） | 消息区先出现 sending → streaming（打字光标）→ 逐字增量 → 完成；meta 后会话列表出现首问标题（前 20 字） |
| E2E-B2 | 回答完成 | 引用卡片区出现依据来源，序号 `[n]` 与正文上标对应；`clickable` 卡片点击 → 「查看原文」弹窗 |
| E2E-B3 | 输入命中敏感词 | 流前同步拦截，报 400 文案（「…包含敏感词…」），不发流不落库 |
| E2E-B4 | 会话管理：重命名（enter 提交 / esc 取消）/ 删除 | 列表标题更新；删除后会话及其消息、引用级联消失（他人资源 404 掩码由后端保证，前端只验正常路径） |
| E2E-B5 | 流式中点「停止生成」 | 已生成内容保留、消息标记失败态「已停止生成」；再次发送可发起 |
| E2E-B6 | 反馈：点「有用」→ 再点 | 状态在 有用→无反馈 间 toggle（幂等，后端 1→1→0 语义在 UI 侧表现为选中态切换） |

### 4.3 流 C：在线考试（选题 → 作答 → 交卷 → 成绩）

| # | 步骤 | 断言 |
|---|---|---|
| E2E-C1 | 公开选卷列表 → 点「开始考试」 | 进入作答页；倒计时显示 `remaining_seconds`（权威值）；题干不含答案/解析（脱敏） |
| E2E-C2 | 作答：单选/多选/判断/填空（`（1）（2）/①②` 占位识别空位） | 每题可作答；FILL 空位数与占位符一致；作答标记 dirtySet 已存 |
| E2E-C3 | 切题/15s 心跳自动保存 | save 请求携带 `{question_id, user_answer}`；切屏>3 次 → 自动交卷提示「切屏超过 3 次，已自动交卷」 |
| E2E-C4 | 交卷 → 成绩单 | 显示成绩与逐题作答/答案/解析；多选漏选显示错误（0 分口径前端只展示结果）；返回记录页 |
| E2E-C5 | 刷新进行中记录 / 交卷后再次进入 | 进行中 → 恢复已存答案继续作答；已交卷 → 幂等回到成绩单（不重评） |

### 4.4 流 D：考试工坊管理端（E01-E03）

| # | 步骤 | 断言 |
|---|---|---|
| E2E-D1 | admin 登录 → 题库：四题型各新建 1 题 → 列表筛选 | 题目 APPROVED 入库；按题型/难度筛选命中；编辑禁改 type |
| E2E-D2 | AI 出题：生成 ≥5 题（mock 档 `page.route` 拦截 `/api/v1/ai/generate` 返回固定 JSON）→ 逐题审核 | PENDING→APPROVED 入库 / REJECTED 驳回；通过率 ≥80% 口径展示 |
| E2E-D3 | 组卷：手动组卷（选题+均分）+ AI 智能组卷（rules 交互）→ 发布 | 发布锁总分/及格线；已发布不可删；员工考试端可见已发布卷 |
| E2E-D4 | 批次审核：整批通过 → 批次列表 → REJECTED 题重写 | batch 状态/通过率更新；重写后原题内容就地更新且状态回 PENDING（不新建批次） |

## 5. 视觉回归（「青石黛」重设计守护）

主题文件 `D:\code\2026\7_8月实训\shudao\frontend\src\style.css`（`:root` 覆写 Element Plus CSS 变量）是唯一品牌源。视觉回归 = **「截图对比 + 关键断言 + 模板色残留扫描」三合一**，全部落在 `tests/visual/`。

### 5.1 回归清单（青石黛六项）

| # | 检查点 | 手段 |
|---|---|---|
| V-01 | 登录页：渐变背景 + 衬线品牌字「蜀道安全助手」 | 截图 + `computedStyle(font-family)` 断言含 `serif`/`Songti SC`；背景含渐变（非纯色） |
| V-02 | 侧栏：玄青底 `#102a28`（`--brand-deep`）+ 黛青胶囊激活项 `#1e5a52`（`--brand`） | 截图 + 断言 `.el-menu` computed `background-color` 与激活项 `background-color` |
| V-03 | 首页模块卡片：单色图标（非彩虹/多色渐变） | 截图 + 断言卡片 icon 不渲染多色 SVG（取色 < 2 种） |
| V-04 | AI 识别面板：`.dot` 编号单色黛青（`--brand-soft` 底 + `--brand` 字），无彩虹七色 | 截图 + 断言 `.dot` `background-color` = `#e6efed`、`color` = `#1e5a52` |
| V-05 | **全局无 AI 模板色残留** | grep 脚本断言为零（见 5.3） |
| V-06 | 核心页面基线（登录/首页/隐患列表+详情/上报/AI 分析/AI 助手/试卷列表/成绩单） | `toHaveScreenshot` 全页对比（maxDiffPixelRatio 0.02，`--update-snapshots` 重录基线） |

### 5.2 截图对比执行约定

- 固定 viewport（1920×1080 与 1280×720 两档）；`page.emulateMedia({ reducedMotion: 'reduce' })` 关动画；登录态用 `storageState` 注入 token（不每页重登）。
- 浏览器 font 渲染跨机器差异大：**基线在同一台机器/同一 base image 录制**，CI 跑在 Docker Playwright 镜像（`mcr.microsoft.com/playwright:v1.x-jammy`）；`maxDiffPixelRatio ≤ 0.02`、`maxDiffPixels` 兜底，防字体微差误报。
- 断言与截图双轨：断言（computed style / class 存在）是硬校验，截图是人眼回归；截图变更需人工确认后 `npm run visual:update` 重录。

### 5.3 模板色残留扫描脚本（V-05，可入 CI gate）

```bash
# 应输出 0 行（src/ 下除 style.css 说明性注释外，禁止出现 AI 模板默认色）
grep -rniE "#409eff|#001529|#ecf5ff|#f0f9eb|#3370ff|#2c3e50|#f5f7fa" \
  --include=*.vue --include=*.css --include=*.ts --include=*.html src/ \
  | grep -v "style.css" || echo "PASS: 无模板色残留"
```

已核实：当前 `src/` 中仅 `src/style.css` 第 9 行注释里出现 `#409eff`（说明文字，非使用），无任何活动色残留。此脚本作为 `package.json` 的 `visual` 前置 gate 或 CI job，防止后续引入 Element Plus 默认蓝/藏青侧栏回归。

## 6. 风险与执行约定

1. **版本兼容**：Vite 8（rolldown）+ Vitest 4.1 为唯一可跑组合，装错版本（Vitest 3.x）会直接启动失败；`@vitejs/plugin-vue` 已为 6.0.8 配套，勿降级。
2. **测试隔离**：hazard store 跨页会话态与 chat `currentId` 是串扰重灾区——所有 store 测试强制 `setActivePinia(createPinia())` + `vi.clearAllMocks()`；jsdom 无 `matchMedia/ResizeObserver`，`setup.ts` 必须补齐否则 Element Plus stub 组件仍可能报错。
3. **SSE/视觉时序**：`utils/sse.ts` 与 `chat store` 是 flaky 高发区——必须 `mock fetch + 受控 ReadableStream + fake timers`，且 rAF 降级为 `setTimeout` 以便推进。
4. **E2E 外部依赖**：SSE 问答/视觉识别默认走 `page.route` mock 档（CI 可重复、零费用）；真 AI 档打 `@tag @ai` 默认跳过，验收时单独 `--grep @ai` 跑。
5. **契约常量**：`CHEAT_LIMIT=3`、`AUTOSAVE_INTERVAL=15`、图片 5MB/9 张、503 视觉降级码、`code!==200` 判失败等与后端对齐的魔法数，测试中统一 `import` 自组件/常量并加注释绑定契约，避免前后端各自漂移（详见「与后端契约的魔法数漂移」风险）。
6. **覆盖率两期**：一期保证「utils 全量 + store 全量 + 6 个核心组件 + 守卫/菜单/cleanParams」通过即合入；二期以 `coverage report` 为准上调 statements ≥60% 并纳入 CI gate。

---


# 第四章 AI 模块专项测试方案（最高风险区）

> 适用对象：模块一视觉识别（`backend/app/ai/vision.py` + `/api/v1/hazards/analyze`）、模块二 RAG 问答（`rag/*` + `service/qa_service.py` + `/api/v1/ai/chat` SSE）、E02 AI 出题/重写（`service/gen_service.py` + `ai/llm_client.py` + `ai/prompts.py` + `ai/doc_extract.py`）。
> 前提：本方案与「后端 API 专项」「后端逻辑单元专项」正交，凡 AI 相关用例统一走 D- 前缀；参数真源以 `config.py`/`rag_config.py` 为准（如 `rag_vec_sim_floor=0.75`、`rag_conf_refuse=0.30`、`rag_conf_conservative=0.45`、`rag_max_rounds=5`、`rag_llm_semaphore=8`、`gen_min_count=5`、`ref_doc_max_chars=5000`、`max_upload_mb=5.0`）。

## .1 测试分层与"真实调用 vs Mock"总原则

AI 模块外部依赖重（LLM API / 视觉 API / Chroma + 本地 bge 模型 / MySQL），测试必须分层，否则不可重复、消耗费用、跑不动。总原则：

| 层 | 依赖 | 结论 |
|---|---|---|
| **纯函数单测** | 无 | 坐标公式、枚举收敛、置信度分类、改写、grounding、prompt 拼串、JSON 解析、doc 解码——零依赖直接断言 |
| **组件单测（打桩）** | mock `AsyncOpenAI` / `chat_stream` / `chat_json` / `get_retriever()` / `get_embedder()` / `get_reranker()` 单例 + 假 Session | 状态机、重试语义、并发背压、降级路径，覆盖"不可重复、非确定性"部分 |
| **集成（真库/真索引）** | 真实 MySQL + `build_knowledge_base.py` 建好的 Chroma/BM25 索引（2544 块） | RRF/BM25/重排链路、citations 落库一致性 |
| **真实调用冒烟** | 真 LLM（DeepSeek）、真视觉 API（百炼）、真图 | 每类**仅 1 条**冒烟，消耗真实费用，CI 可手动触发不默认跑 |

边界裁决：**凡输入可构造、输出可由代码校验的分支一律 mock；只有"输出质量本身"（检索召回率、幻觉率、题面正确率、识别准确性）必须真实调用**。坐标数学与 LLM 解析是"校验逻辑"，零依赖；图片内容理解与题面质量是"语义"，必须真调。

---

## .2 视觉识别（vision.py + hazards/analyze）

链路：`_save_upload`（白名单+MIME+≤5MB 落盘）→ `_square_b64image`（EXIF 转正→居中 pad 正方形→JPEG base64）→ 视觉 LLM（timeout 240s，退避重试 2s/4s）→ `_sanitize` → `_remap_detections`（坐标反算回原图）→ `annotate_image`（画框标注图）→ 落 `risk_report` 返回。未配置 `VISION_BASE_URL/API_KEY/MODEL_NAME` 任一为空 → `VisionError` → **503**，不阻断手动上报。

### .2.1 非方形图坐标重映射正确性（最高优先）

**背景**：模型输入是 `S=max(W,H)` 正方形画布（内容居中，偏移 `x_off=(S-W)//2, y_off=(S-H)//2`），模型返回画布归一化坐标，经 `_to_original_bbox` 反算回原图：`left=(min(x1,x2)*S-x_off)/W`、`top=(min(y1,y2)*S-y_off)/H`，越界钳 `[0,1]`，映射后宽/高 <0.02 判 None。

**测试方法（两层）**：
- **纯公式单测**：直接调 `_to_original_bbox(bbox, W,H,S,x_off,y_off)`。构造已知 geom 断言手算值。
  - 横图 `800×400`：`S=800,x_off=0,y_off=200`，画布框 `[0.0,0.0,0.5,0.5]` → `[0,0,0.5,0.5]`（画布左上四分之一正好是内容带 y∈[0,0.5]）。
  - 竖图 `400×800`：`S=800,x_off=200,y_off=0`，画布框 `[0.5,0.25,1.0,0.75]` → left=0.5、top=0.25、right=1.0（越界钳制）、bottom=0.75。
- **round-trip 集成单测（PIL 真图 + mock AsyncOpenAI）**：用 PIL 造一张 `W×H` 图，在**原图归一化坐标** `[0.2,0.3,0.6,0.8]` 处画红矩形；先跑 `_square_b64image` 得 `geom`，按正变换 `x_canvas=(x_orig*W+x_off)/S, y_canvas=(y_orig*H+y_off)/S` 算画布框；mock `AsyncOpenAI.chat.completions.create` 返回该画布框 → 走 `analyze_image`（或直接 `_remap_detections`）→ 断言 remap 后坐标与 `[0.2,0.3,0.6,0.8]` 一致（4 位小数容差）。此用例验证「pad 逆映射 + 四舍五入 + 顺序归一化」整条不被破坏。

**异常分支**：`len!=4`、非数字 → None；坐标排序（左>右自动交换）；映射后宽/高 <0.02（被画布边缘裁掉）→ None；越界钳 `[0,1]`。

### .2.2 无隐患空结果

mock 视觉模型返回 `{"detections":[]}` 或旧格式无 `type/bbox/level` 的对象 → `_sanitize` 收敛为 `detections=[]`、`bbox=None`、`type_suggest=其他`、`level_suggest=MINOR`；`annotate_image` 无有效框返回 None（`annotated_url=null`）；前端不渲染识别卡。构造"干净场景图"做真实冒烟时同样断言空分支。

### .2.3 多图识别顺序与超时

- **顺序**：后端 analyze 为单图接口，前端批量逐张顺序调用。后端单测：mock 视觉响应含 2 处检测（`detections` 数组、旧格式裸对象两种形状），断言 `_sanitize` 按 confidence 降序、最多 4 处；连续两次调用各自结果独立不串（每次新 `analyze_image`）。
- **超时（客户端 240s / 服务端 290s）**：`analyze_image` 内 `AsyncOpenAI(timeout=240.0)`，api 层 `asyncio.wait_for(..., timeout=290.0)` 兜底。测试用 mock 响应挂起 >240s（假 sleep/慢生成器）触发 `asyncio.TimeoutError` → 503「视觉识别超时，请重试或跳过」。**必须用短可控假时钟（monkeypatch `asyncio.sleep`），290s 实等不可接受**。
- **重试**：mock `_RETRYABLE`（APIConnectionError/APITimeoutError/RateLimitError/APIStatusError/httpx.HTTPError）→ 断言退避 2s/4s 重试 2 次后 `VisionError`；JSON 解析失败（`_extract_json` 抛）→ **不重试**直接 `VisionError`；鉴权类 `OpenAIError` → 不重试。

### .2.4 未配置 503 降级（不阻断上报）

- 清空 `.env` 中 `VISION_*`（或用 `get_settings` 覆盖）→ `POST /hazards/analyze` 返回 **503** `{code,message,data:null}`。
- 紧接 `POST /hazards` 纯手动上报（不带 risk_report）→ **200**，编号 `HZ+日期` 正常生成、状态 `WAIT_PROCESS`——验证降级不阻断主流程。

### .2.5 白名单与大小校验

`_save_upload`：扩展名 `.jpg/.png/.jpeg` + MIME 白名单双校验、`≤5MB`、uuid 文件名 + `YYYYMMDD` 子目录防穿越。用例：`.gif` 扩展名 →400；改后缀但 content-type 非图片 →400；构造 >5MB 文件 →400；返回 `/uploads/{day}/{uuid}.jpg`。

### .2.6 标注图 URL 可访问

`annotate_image` 画框落盘 `uploads/{day}/annotated/{uuid}.png`。用例：识别含 2 处检测 → `annotated_url` 非空且 `GET /uploads/{day}/annotated/{x}.png` 返回 200 与 `image/png`；内容含矩形（可读回 PNG 用 PIL 校验红色框存在）；字体缺失（mock `_cjk_font` 返回 None）→ 只画框不抛错；`annotate_image` 内部异常 → 返回 None 不阻断。

---

## .3 RAG 检索质量（rag/* + qa_service）

### .3.1 评测集方法（标定思路）

参照 `docs/RAG优化方案.md` §0.2/§5 与 `data/calibrate_refusal.py` 标定思路。**注意：`backend/data/calibrate_refusal.py` 当前仓库不存在**（仅为方案引用的标定脚本名），本方案把该标定装置定义为待建测试基建，方法如下：

- **两级评测集**：CI 冒烟集 **200 问 + 30 拒答**（秒级，每次改动必跑）；完整回归集 **问答 3100（法规 2200+场景 600+边界拒答 300）+ 多轮 300 + 出题专项 620**（上线门禁）。评测集版本化冻结，`baseline.json` git 存档。
- **指标口径（对齐方案）**：检索 `Recall@5≥0.92 / MRR≥0.85 / NDCG@5≥0.90 / 命中条号正确率≥0.95 / top-1 命中≥0.70`；生成 `引用覆盖率≥95% / 引用可核验率100% / 幻觉率≤5% / 拒答正确率≥95%`。
- **自动化红利**：2087 条均带"第X条"编号，**条号即答案**——命中条号正确率、引用正确率（回答引用条号 ⊆ 检索块条号，正则抽取比对）、拒答正确率、多选格式全部规则层零成本全量必跑；忠实度/幻觉率用 **LLM-as-judge 抽样 30%**，judge 模型固定独立来源（qwen-plus/GLM-4），prompt 模板固定。
- **阈值联合标定**：`classify` 的 0.30/0.45 与 `top_vec_sim` 的 0.75 属同一链路不同环节，标定时一组阈值一次回归（召回率 vs 拒答率 trade-off 曲线），不孤立调参；变更必须过 §5.7 回归门禁（回退 >1pt 阻断）。

落地建议：冒烟 200+30 作为 pytest 标记 `@pytest.mark.smoke_rag`，数据存 `backend/tests/eval/` JSON；每次改动跑；完整 3100 单独脚本（真库+真 LLM，费用可控批次）。

### .3.2 拒答/保守边界（可 mock，纯逻辑）

- **`classify(conf, refuse=0.30, conservative=0.45)` 严格小于**：`0.299→refuse`、`0.30→conservative`、`0.449→conservative`、`0.45→full`、`0.451→full`（边界恰在阈值上属保守/全量，不误拒）。
- **`top_vec_sim < 0.75` 绝对拒答**：`qa_service` 中 `low_sim = result.top_vec_sim < vec_sim_floor`，即便检索到块也拒答（防"检索到但无关"幻觉）。用例：mock `retriever.search` 返回 `top_vec_sim=0.74` 且 blocks 非空 → 流输出 `mode=refuse` 固定话术、`citations=[]`、`grounding=0.0`、**`chat_stream` 未被调用**（patch 计数断言）。
- **检索为空拒答**：`blocks=[]` → 同上固定话术（"知识库中暂未找到相关内容"语义），不调 LLM。

### .3.3 RRF/BM25/重排链路（mock 组件 + 真 Chroma fixture）

流水线：向量 Top-50 + BM25 Top-50 → RRF(K=60) Top-20 → 交叉引用展开（Top-3 ref_out）→ bge-reranker Top-5 → 置信度 `confidence=min(1, top_rrf*(K+1)/2)`。测试方法：
- **mock 单例**：`monkeypatch` `get_embedder`（返回固定向量）、`get_reranker`（返回固定重排序）、`get_retriever` 内部用**小型 Chroma fixture**（`PersistentClient` 临时目录，灌 5-10 个块含父子块/ref_out/access_level），避免加载分钟级真索引。
- **断言**：融合结果父块粒度（子块回溯父块取 max）；`top_vec_sim=1-distance` 取向量路 top-1 绝对相似度；confidence 相对峰值公式；`mode` 落档正确。
- **边界**：RRF 数学内联未抽纯函数，只能 mock 组件集成断言（已在盘点标注）；`normalize_rrf`（min-max）为日志用，与 `confidence`（相对峰值）是**两套归一化并存**，测试须分别断言并注明仅一套进 mode。
- **交叉引用展开**：Top-3 含 `ref_out` → 查回父块（`expanded=true`），不二次展开；access_level 过滤（MVP 全公开）。

### .3.4 多轮上下文轮数

`rewriter.should_rewrite`：含指代词（它/该/那/此/其/上述…）即触发；轮次 ≥2 且问 ≤6 字触发。`rewrite_query` 取最近 `rag_max_rounds=5` 轮非空问句按 `；` 拼接 + 当前问。测试：5 轮历史全拼接、>5 轮只取最近 5、`rewritten_used` 打标、未触发原样返回；`qa_service` 中改写串进检索、原文进 BM25 双路（`kw_queries` 构造断言）。集成冒烟：第 6 轮问"它的适用范围是什么"（含"它"）→ meta.rewritten_used=true。

### .3.5 敏感词过滤

`contains_sensitive`（词库 `backend/data/sensitive_words.txt`，`#`注释/空行跳过，`lru_cache` 进程级缓存）。用例：命中词 → `POST /chat` **400**（`内容包含敏感词：xxx`），**在流开始前同步执行，不进检索/LLM**（patch retriever 断言未调用）；词库空/文本空 → `[]` 放行；跨用例清缓存（`load_sensitive_words.cache_clear()`）。

### .3.6 citations 引用与原文可读

- `build_citations`：块序号 n 从 1 起与 prompt `[n]` 对齐，`snippet=content[:400]`（父块=整条，多数条 <400 字即全量展示），无章节/条号字段可为空串。
- `done.citations` 与 `meta.citations` 一致、与 SSE 期间 `[n]` 脚注一一对应；落库 `message_source`（含 `doc_id/article_no` 原文定位列）join `knowledge_chunk/document`，`chunk_id=vector_id` 三者一致（引用 G3）。历史消息 sources 带 `doc_id/article_no` → 前端 `clickable=true` 可点开查看原文；旧数据两列为 NULL 则不可点击。
- `GET /api/v1/ai/article`（`doc_id+article_no` 必填）→ 检索层父块全文 + 出处字段，无 DB 归属校验；`doc_id/article_no` 不存在 → 404。真实冒烟：问一条具体条文 → 引用卡序号、点击查看原文、内容与 `[n]` 所指一致。

### .3.7 SSE 保活 ping 与并发信号量背压

- **ping**：`config.rag_stream_ping_sec=60`，契约声明"LLM 静默 60s 发 `{type:ping}`"。**实现缺口已核实**：`qa_service.stream_qa` 仅产出 `meta→delta*→done`，**当前代码未发出任何 ping 帧**（`_sse` 无 ping 调用）。用例 D-23 记录现状并标记为**待与实现方核验的契约偏差**，断言以实际行为为准（无 ping 帧）；若后续实现，用受控慢流（每 65s 一 chunk）断言 ping 插入且不打断 delta 序。
- **背压**：`_LLM_SEMAPHORE = Semaphore(8)`。用例：mock `chat_stream` 用 `asyncio.Semaphore` 计数器记录并发进入峰值，同时发起 ≥10 个流的并发请求（真 asyncio.gather，mock DB 写）→ 峰值 ≤8；同一会话并发问答由 `_conv_lock` 串行（第二次请求的 user 消息先落库、历史读不到第一次结果）。
- **SSE 响应头**：`media_type=text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`。

---

## .4 LLM / 出题（gen_service / llm_client / doc_extract / prompts）

### .4.1 prompt 稳定性

`build_generate_prompt` / `build_rewrite_prompt` / `build_qa_prompt` / `_format_articles` / `_format_blocks` / `_format_history` 均为纯字符串构造。测试方法：固定入参 → **快照比对**（黄金文本 git 存档），防"无意识改动导致 LLM 输出漂移"；逐项断言要点——题量分配文本、`[n]` 序号与引用卡片对齐、保守模式 `max_tokens` 收紧至 300（`conservative_tokens`）、参考文档块插入与规则 8-10、重写 prompt 含原题 JSON+驳回原因+修订要求、FILL/JUDGE 选项约束。入参边界：空 `types`/`count<1`/空 `knowledge_point` → `ValueError`。

### .4.2 JSON 输出解析容错

`_extract_json`：空串→LLMError；剥 ```json/``` 围栏；顶层非 dict（列表/标量）→LLMError；JSONDecodeError→LLMError。分层测试：
- **llm_client 层**：剥围栏/顶层非对象 → LLMError，**不重试**（`max_retries` 不生效）。
- **gen 层**：`GenOutput.model_validate` 失败 → 自动重生成（`_MAX_ATTEMPTS=3`），3 次仍败 → **502**（`AI 输出不符合要求`）。
- **重写层**：`_extract_single_question` 兼容 `questions` 数组/裸对象；`_finalize_rewrite` 题型与原题不一致 / 溯源不在知识库 / 原样复述 → `_RewriteRetry` 触发带 `strengthen` 强化指令的重试，仍败 → 502。
- **拒答层**：grounding 越界 `[n]` 删除（`_ground`），`total==0` → 0 分不重生成。

### .4.3 超时与重试

- `chat_json`：未配置（BASE_URL/API_KEY/MODEL_NAME 任一空）→ LLMError；`_RETRYABLE` 指数退避 `2^attempt`（2s/4s）重试 `max_retries=2` 后抛；`OpenAIError`（鉴权/参数）不重试。**测试用 mock AsyncOpenAI**，对前 N 次抛 `APITimeoutError` 断言退避 sleep 调用序列与最终 LLMError。
- `chat_stream`：**首块前**可重试 1 次；已出流后任何中断 → 直接 LLMError（SSE 断点续传不可靠语义）。用例：mock 流先 yield 一个增量再抛网络错误 → `qa_service` 落 `FAILED` 且 `done.error` 带提示；首块前抛网络错误 → 重试成功正常出流。

### .4.4 ref_doc 截断与 token 上限

- `reference_text` schema `max_length=6000`，后端 `ref_doc_max_chars=5000` 截断并 `truncated=true`；检索词取 `kp or ref[:64]`；`build_generate_prompt` 插入【参考文档】块。
- `chat_stream` 全量 `max_tokens=800`、保守 300；`_estimate_tokens = max(1, len/1.5)`。
- `doc_extract`：txt/md 三级解码（utf-8 严格→gbk→utf-8 replace）；非法扩展名→`ValueError`（含「不支持的文档类型」）→400；pdf/docx 延迟导入缺依赖→`ImportError`→500。

### .4.5 模型未就绪降级

- LLM 未配置 → `generate`/`rewrite` **502**、`chat` 流内 `done.error`（非 HTTP 500，SSE 已开流）。
- 视觉未配置 → analyze **503**（见 §4.2.4）。
- RAG 本地模型未就绪（lifespan 预热失败仅告警）→ 运行时 `get_retriever()` 抛 `RuntimeError`（Chroma 集合为空）→ chat 流前 **500**。用例：清空/损坏 Chroma fixture → 断言失败消息；正常路径不受影响。

---

## .5 真实调用 vs Mock 边界汇总

| 测试对象 | 方式 | 说明 |
|---|---|---|
| `_to_original_bbox` / `_sanitize_bbox` / `_sanitize_detection` / `_remap_detections` | **纯单测** | 手算公式断言 + round-trip（PIL 真图 + mock 视觉模型） |
| `classify` / `normalize_rrf` / `rewriter` / `_ground` / `_extract_json` / `_allocate` / prompts / `_decode_text` / `contains_sensitive` | **纯单测** | 零依赖 |
| `analyze_image`（未配置/超时/重试/空结果） | **mock** `AsyncOpenAI` + 真 PIL 图 | 挂起用假时钟 |
| `annotate_image` | **真 PIL** + 临时 uploads 目录 | 真落盘断言 URL |
| `stream_qa`（拒答/事件序/FAILED/INTERRUPTED/背压） | **mock** `chat_stream` + `get_retriever` + 假 Session | patch 计数断言不调 LLM |
| `retriever.search`（RRF/BM25/重排/展开） | **mock** embedder/reranker 单例 + 小型 Chroma fixture | 不加载真索引 |
| `chat_json` / `chat_stream` 重试语义 | **mock** `AsyncOpenAI` | 断言退避 sleep 序列 |
| `gen_service.generate/rewrite` | **mock** `chat_json` + 真/内存 MySQL + mock `load_corpus` | 断言批量/状态机/502/409 |
| `doc_extract` pdf/docx | 造真 pdf/docx 字节（有依赖）或 mock 依赖缺失分支 | |
| 视觉真实识别 / RAG 检索质量 / AI 出题 / SSE 全链路 | **真实调用冒烟** | 每类 1 条；评测集 200+30 / 3100 按门禁脚本 |

---

# 第五章 安全测试 · 性能测试 · 手工验收（UAT）

## 0. 章节定位与前置约定

本章节覆盖三类非功能/验收测试：**安全测试**（以越权、注入、上传、XSS、密钥保护为核心）、**性能与可靠性测试**（响应基线、并发、慢查询、SSE 长连接、降级可用性）、**手工验收 UAT**（按模块逐场景验收，含「蜀道·青石黛」视觉重设计专项）。

前置约定（沿用盘点结论）：

- 后端按 `backend/app/core/config.py` + `backend/app/main.py` + `backend/app/api/*` 的实际实现为准；数据库结构以 `backend/database/schema.sql` 为准，勿照 `docs/DATABASE.md §9`（已过时）。
- 测试库需独立隔离（独立 schema 或前缀命名 + 事务回滚），避免与 `test_*_e2e.py` 共享数据；AI/视觉相关用例分「真调用」与「mock 降级」两档，真调用每次消耗外部 API 费用。
- 测试环境须以 `backend/.env`（gitignored）注入真实凭据；不配置时 LLM 三组 key 任一为空即 `generate/rewrite→502`、`analyze→503`、`chat 流→500`，这正是降级路径的天然开关。
- 前端安全重点为 `utils/markdown.ts renderMarkdown`（marked→DOMPurify 唯一净化管线）及 `MarkdownRenderer/QuestionCard/ExamResult/ArticleDialog` 四处 `v-html` 消费点。
- 性能验收口径以 `docs/PRD.md §6.1` 与 RAG 方案 §6.8 为基准：并发 ≥50 QPS、AI 首字（SSE 首包）≤3s、API P95 ≤500ms、前端首屏 ≤2s。当前无 Locust/k6/pytest-cov 载体，需先行补装。

---

## 1. 安全测试

### 1.1 测试目标

验证系统在「未登录/越权/伪造令牌/恶意上传/XSS/路径穿越/凭据泄露」七类攻击面下均按契约拒绝，且错误响应与日志不泄露敏感信息；明确已知安全缺口的实际行为（不掩盖）。

### 1.2 安全测试用例表

| 编号 | 用例 | 前置/环境 | 测试步骤 | 预期结果 |
|---|---|---|---|---|
| S-01 | JWT 占位密钥防伪 | `.env` 不设 `JWT_SECRET` 或设为 `_PLACEHOLDER_SECRETS` 中任意串 | ① 启动后打印进程内 `settings.jwt_secret` 是否被替换为随机值；② 用源码已知占位串离线签名 `{sub:1,exp:now+60m}` 访问 `/auth/me` | ① 已替换为 `secrets.token_urlsafe(48)` 随机密钥；② 访问返回 401，无法伪造通过 |
| S-02 | JWT 过期 | 正常登录 | 用 `JWT_EXPIRE_MINUTES=0` 临时签发或用工具生成 `exp` 已过的 token 访问 `/auth/me` | 401（`_CRED_EXC`），统一 `{code:401,message,data:null}` |
| S-03 | JWT 篡改/异密钥 | 正常登录 | ① 改 payload `sub`；② 用无关随机密钥签名同 payload | 均 401，不返回用户信息 |
| S-04 | 禁用账号即时失效 | 登录后改 `user.status=2` | 用未过期 token 访问 `/auth/me` | 401，不等 120 分钟过期（`get_current_user` 复核状态） |
| S-05 | 弱口令/密码策略 | 公开注册接口 | ① 密码 <6 位；② 密码 >64 位；③ 密码 ≤64 字符但 utf-8 >72 字节（如 30 个「密」=90 字节）；④ 用户名 <3 位 | ①④ 422；② 422（长度校验）；③ 400「密码不合法」（bcrypt 上限，hash_password 显式 400） |
| S-06 | 越权-角色（管理接口 403） | 员工/安全员/管理员三账号 | EMPLOYEE 调 `POST /questions`、`POST /papers/manual`、`POST /ai/generate`、`POST /hazards/{hid}/close` | 员工全 403（`require_roles` 门禁，`{code:403,...}`）；SAFETY/ADMIN 放行 |
| S-07 | 越权-他人资源（404 掩码） | 用户 A、B 各自登录 | A 访问/删除/引用/反馈 B 的会话与消息、A 调 `GET /exams/{B 的 record_id}`、`PUT/DELETE /ai/conversations/{B 的 cid}` | 统一 404，且 B 的资源是否存在返回一致（防枚举，不区分 404/403 语义差异暴露存在性） |
| S-08 | 未登录 401 | 无 token | 访问 `/auth/me`、`/hazards`、`/ai/chat`、`/exams/records` 等业务接口 | 401 统一 `{code,message,data}`；`GET /`、`/uploads/*`、`/docs` 公开可访问 |
| S-09 | 上传白名单-类型 | 已登录 | ① 上传 `.gif`/`.svg`/`.html`/无扩展名 → `/hazards/upload`；② 扩展名 `.jpg` 但 `Content-Type=text/html`；③ 合法 jpg | ①② 400（扩展名或 MIME 双白名单拦截，`hazard.py` 双校验）；③ 200 返回 `/uploads/...` URL |
| S-10 | 上传大小-超限 | 已登录 | ① 图片 >5MB → `/hazards/upload`；② 文档 >5MB → `/ai/doc`；③ 恰好 ≤5MB | ① 400「图片超过大小上限」；② 413「文档过大（上限 5MB）」；③ 200 |
| S-11 | 上传路径穿越/静态暴露 | 已登录 + 磁盘探测 | ① 文件名 `../../evil.jpg` 上传 → 检查落盘路径；② 直接访问 `/uploads/../../../backend/app/main.py`、`/uploads/..%2f..`；③ 枚举 `YYYYMMDD` 子目录 | ① 落盘为 `uuid4().hex.jpg` + 按日期子目录，无 `../` 逃逸；② 均 404，无法越出 uploads 目录；③ 仅本日期文件可访问（静态挂载限目录） |
| S-12 | 凭据不落库/不打印 | 生产环境 `.env` | ① 错误密码登录，检查错误响应体；② 触发 `analyze` 503 与 `generate` 502，抓响应体；③ grep uvicorn 日志关键词 `sk-|api_key|DATABASE_URL|password|VISION_`；④ `git ls-files` 检查 .env 入库情况 | ①② 响应体不含连接串/API Key/模型名泄露；③ 日志无真实凭据（`config.py` 不打印，仅告警文案）；④ `.env` 不在 git 追踪（.gitignore 命中 `.env`/`.env.*`） |
| S-13 | XSS-Markdown 净化 | 前端（jsdom） | 对 `renderMarkdown` 投递 `<img src=x onerror=alert(1)>`、`<script>alert(1)</script>`、`[x](javascript:alert(1))`、`<svg onload=...>` | 渲染结果被 DOMPurify 剥离危险标签/属性，无 `onerror`/`javascript:`/`script` 存活；`MarkdownRenderer` 净化后追加的 `[n]→<sup>` 只匹配 `\d{1,3}` 不受注入影响 |
| S-14 | XSS-文件名/图片路径 | 前端 | 隐患上报文件名含 `<script>`；识别图 `src` 指向 `javascript:`/`data:` 伪造协议 | 文件名按纯文本渲染不执行；图片 src 仅接受 `/uploads/` 相对路径或 http(s)，非法协议不加载（v-html 四消费点回归） |
| S-15 | CORS 配置 | 任意 | 跨域请求携带 `Origin: http://evil.example`；预检 `OPTIONS` | `Access-Control-Allow-Origin: *`、`Allow-Credentials` 缺省 false（`allow_credentials=False`），方法与头全开——符合开发放开契约，生产收紧项另记 |
| S-16 | SSE 接口鉴权 | 未登录/已登录 | ① 无 token `POST /ai/chat`；② 有效 token 检查响应头；③ 敏感词命中流前拦截 | ① 401 且不产生任何流帧；② `Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`；③ 流开始前同步 400，不进检索/LLM |
| S-17 | 敏感词入口拦截 | 已登录 | 问答文本含敏感词 | 400 且日志/检索/LLM 均不触发（敏感词预检在流前） |
| S-18 | 全局异常处理缺口（行为确认） | 服务层抛异常 | 注入 ValueError/`IntegrityError`/MySQL 断连触发 500 | 返回 FastAPI 默认 500 格式而非 `{code,message,data}`——记录为已知缺口（未规范化），不阻断功能 |
| S-19 | 注册强制员工角色 | 公开 | 注册请求带 `role_id=3`（ADMIN）或省略 | 服务端忽略并强制 `role_id=1`（EMPLOYEE），无法自注册管理员；重复用户名 400（撞 `uk_username`） |

### 1.3 安全结论与已知缺口

- **通过项**：JWT 占位密钥防伪、密码 bcrypt cost=12、双白名单上传、uuid+日期子目录防穿越、404 归属掩码、SSE 全接口鉴权、DOMPurify 单管线净化、敏感词流前拦截。
- **已知缺口（需在验收报告中显式标注，不误报为通过）**：① 服务层未捕获异常返回 FastAPI 默认 500 而非 `{code,message,data}`，错误格式不一致；② `CORS allow_origins=["*"]` 为开发放开，生产须收紧；③ `/uploads` 与 `/docs` 为公开挂载，无内容访问审计；④ Redis 未实际接入（`config.py` 有配置但 service 未使用），E04 会话为 DB 存储，安全测试不依赖 Redis。

---

## 2. 性能与可靠性测试

> 压测载体：当前仓库无 Locust/k6。方案落地步骤为 ① `pip install locust` 或 k6；② 独立压测库（数据量≥5 万）；③ 先单接口基准，再混合场景。下述基线均以 P95 计，前端/后端分别测量。
>
> **验收门禁（对齐任务书 §4.4 并发≥50 与 PRD §6.1）**：对三个关键接口设最低硬门禁——`POST /auth/login`（100 并发 P95≤500ms 且 ≥50 QPS）、`GET /hazards`（5 万条 page_size=20 P95≤500ms）、`POST /ai/chat` 首包（meta 首帧 ≤3s；mock LLM 档测编排、真 LLM 档测首字）。其余接口仅打点基线。门禁写进 CI（Locust/k6 脚本），失败阻断发布。

### 2.1 关键接口响应时间基线

| 接口 | 场景 | 目标 | 说明 |
|---|---|---|---|
| `POST /auth/login` | 100 并发 × 5 轮 | P95 ≤500ms，≥50 QPS | bcrypt cost=12 为 CPU 密集，瓶颈在哈希 |
| `GET /hazards` | 5 万条数据, page_size=20 | P95 ≤500ms | 含筛选/分页/排序 |
| `GET /hazards/{hid}` | 热记录 | P95 ≤300ms | 含图片 + 时间线 |
| `GET /questions` | 分页 page_size=20 | P95 ≤500ms | 多条件筛选 |
| `GET /exams/records` | 分页 | P95 ≤500ms | |
| `POST /ai/chat`（首包） | 20 轮真/伪 LLM | 首帧 meta ≤3s | 含 LLM 首块；需分流 mock 与真调用两档基线 |
| 前端首屏 `/login`、`/home` | 冷缓存 | ≤2s | 测量工具：Playwright `page.goto(..., waitUntil:'load')` + `performance.timing`（或 Lighthouse CI）；口径=无缓存冷启动 load→可交互；预算断言写进 CI，超时标 P1 |

### 2.2 大页分页

- 边界：`page ≤ 100000`、`page_size ≤ 100`（`papers.py`/`hazards.py`/`questions` 等统一防 OFFSET 溢出）。
- 用例：`page=99999&page_size=100` → 200 不溢出；`page=100001` → 422；`page_size=101` → 422。
- 深页性能：在 5 万行数据上对比 `page=1000` 与 `page=50000` 的响应时间——OFFSET 深翻页会线性劣化，记录该观测并给出建议（keyset/游标分页）而非断言必过。

### 2.3 并发上传与识别

- 上传：10 线程 × 5 张并发 `POST /hazards/upload` → 全部 200，`uuid` 无碰撞、`YYYYMMDD` 子目录正确、无文件互相覆盖。
- 识别：`POST /hazards/analyze` 并发 10（VISION 已配置真调用档）→ 单张 290s 超时保护生效，重试 2 次（2s/4s）语义正确；降级档（VISION 未配置）→ 并发 10 全部 503，服务不崩，且 `POST /hazards` 上报不受影响（503 不阻断上报的契约）。
- 记录项：视觉识别为外部 API，压测注意限流与费用，建议 mock 档为主、真调用抽样。

### 2.4 数据库慢查询与索引覆盖（EXPLAIN 核验）

| 表 | 高频筛选/排序列 | 核验点（SHOW INDEX + EXPLAIN） |
|---|---|---|
| question | type/difficulty/knowledge_point/status/source/batch_id + 分页 | 组合筛选是否命中索引；`knowledge_point` 等未建索引列是否引发全表扫 |
| hazard | status/level/type + create_time 区间 + keyword + 分页排序 | `sort=level`/`create_time` 排序是否走索引或 filesort |
| message | conversation_id + id | 会话消息拉取是否命中索引（含级联删除范围） |
| exam_record | user_id + state（uk_user_paper_ongoing） | 我的记录分页、进行中唯一约束是否走索引 |
| exam_answer | record_id（uk_record_question） | 明细 upsert 与判分批量读是否命中 |
| hazard_log | hazard_id | 详情时间线查询 |
| knowledge_chunk | doc_id | 溯源 join、article 原文查回 |

结论输出：列出「已命中索引」与「存在全表扫描风险的列」两类清单，作为 `schema.sql` 索引补充依据。

### 2.5 SSE 长连接与断线重连

- 长连接：LLM 静默 >60s 时收到 `ping{type}` 心跳帧，连接不被代理/浏览器切断；`X-Accel-Buffering: no` 防 Nginx 缓冲。
- 断线：客户端中途断开（AbortController / 关页）→ 服务端将该消息落为 `INTERRUPTED`（已出流中断直接 FAILED）；`GET /ai/conversations/{cid}/messages` 重进可查；未完成消息不残留 `streaming` 标记（chat store `finally` 兜底成功/失败）。
- 重连：`chatSSE` 用 fetch 手带 `Authorization`，非 `text/event-stream` 响应与畸形帧映射错误文案不误报成功。

### 2.6 503 降级可用性

- 触发：VISION key 未配置 / 外部视觉超时 → `analyze` 503；LLM key 未配置 → `generate/rewrite` 502、`chat` 流 500。
- 验证：降级期间 ① `POST /hazards`（纯文字上报）仍 200；② `POST /hazards/upload` 仍 200；③ 登录/列表/详情等非 AI 接口全绿；④ 前端显示 `aiDown` 降级提示且「AI 识别→上报」链路可用手动录入兜底。
- 可靠性：MySQL 断连 → 接口 500（FastAPI 默认）不抛裸堆栈、恢复后无僵尸连接；`lifespan` 预热失败仅告警不阻断启动（`chat` 届时 500）。

---

## 3. 手工验收（UAT）清单

> 验收角色：管理员（admin/ADMIN=3）、安全员（SAFETY=2）、普通员工（EMPLOYEE=1）、禁用账号各一。验收环境：`backend` 8000 端口 + 真 MySQL + `.env` 真实 LLM/VISION（AI 类用例）。

### 3.1 基础支撑 B01-B03

| 场景 | 验收步骤 | 预期 |
|---|---|---|
| B01 注册/登录 | 注册新员工→登录→`/auth/me` 显示本人 | 注册成功即登录态；弱口令被拒（S-05）；JWT 120 分钟有效 |
| B02 角色权限 | 员工登录查侧栏菜单 | 员工仅见隐患/问答/考试端入口，管理页（题库/AI 出题/试卷）不可见或访问被 403 拦 |
| B03 文件上传 | 依次传 jpg/png/gif/svg/>5MB 文件 | jpg/png 成功、gif/svg/超限被前端 beforeUpload 预校验拦截（后端 400 兜底） |

### 3.2 模块一 隐患安全（H01-H03）

| 场景 | 验收步骤 | 预期 |
|---|---|---|
| H01 上报 | 带图上报（等级 CRITICAL/MAJOR/GENERAL/MINOR）+ 纯文字上报 | 编号 `HZ+日期-序号` 唯一递增；初始状态 WAIT_PROCESS；位置空落「未填写」；描述空 422 |
| H01 多图 | 上传 ≤9 张图片再上报 | 全部回显；第 10 张被拦截（前端 9 张上限 + 后端校验） |
| H01 视觉识别 | 上传现场图 → AI 分析 → 结果「应用到表单」→ 上报提交 | 识别面板显示识别建议/明细/标注图；应用后描述/等级/图片回填且一次性消费（再进上报页不残留）；VISION 未配置时显示降级提示，可手动录入兜底上报成功 |
| H02 列表 | 状态/等级/类型/关键字/时间区间五维筛选 + 列头排序 + 分页 | 组合筛选结果正确；排序 `create_time/level` × `asc/desc`；翻页不重不漏 |
| H03 详情 | 进入详情看时间线与图片 | 时间线倒序；员工点「闭环」→ 403；管理员闭环 → 状态变 FINISHED + 留痕；重复闭环 → 400 |

### 3.3 模块二 AI 助手（A01-A03）

| 场景 | 验收步骤 | 预期 |
|---|---|---|
| A01 问答 | 提问法规问题（如「高处作业安全带要求」） | SSE meta→delta→done 逐帧输出；done 带 citations 且与正文 `[n]` 一一对应；`synthetic=true`；来源引用可点开查看原文 |
| A01 多轮/拒答 | 连续 5 轮追问含指代（「那罚款呢」） | 指代消解成功（rewritten_used）；知识库外问题返回「知识库中暂未找到相关内容」且不调 LLM |
| A02 会话管理 | 新建/列表/重命名/删除 | 新建空对话标题「新会话」；按更新时间倒序；删除级联清空消息与引用；他人会话 404 |
| A03 流式输出 | 断网/中途停止 | 停止后无残留 streaming 标记；恢复后历史完整；敏感词提问被 400 拦截 |

### 3.4 模块三 考试工坊（E01-E05）

| 场景 | 验收步骤 | 预期 |
|---|---|---|
| E01 题库 CRUD | 四题型新建/编辑/删除/筛选 | 单选/多选/判断/填空均可建改删；编辑禁改 type；正确答案与解析必填；被试卷引用题目不可删（400） |
| E02 AI 出题 | 管理员生成 ≥5 题→审核 | 单次生成 ≥5 题同 batch_id；PENDING→APPROVED 入库；通过率 ≥80% 口径展示；REJECTED 题可带意见重写（新题 PENDING、rewrite_of 关联） |
| E03 组卷 | 手动组卷 + AI 智能组卷 | 手动组卷分值均分、及格线 ≤ 总分校验（>总分 422）；AI 组卷按题型/难度/知识点抽题；发布后锁定总分/及格线；已发布禁删 |
| E04 在线考试 | 员工选卷开考→答题→切屏→交卷 | 倒计时以服务端 `remaining_seconds` 为权威；15s+切题自动保存；刷新恢复现场；第 4 次切屏自动交卷（reason=cheat_limit）；超时自动交卷（reason=timeout） |
| E05 自动阅卷 | 交卷看成绩单 | 客观题自动评分；多选全对得分/漏选错选 0 分；成绩单含逐题作答+答案+解析+AI 合成标识；双开两窗口并发交卷只评一次、分数一致 |

### 3.5 「蜀道·青石黛」视觉重设计验收（专项）

> 验收基准 = `frontend/src/style.css` :root 设计 token + `docs/frontend_design/00~05`。目标观感：专业沉稳的安全管控平台，消除「AI 模板感」（默认蓝/藏青侧栏/彩虹色块）。

| 验收点 | 验收内容 | 预期（对照 token 值） |
|---|---|---|
| 全局色值 | 品牌主色替换默认蓝 | 全局主色 `--el-color-primary: #1e5a52`（黛青），默认蓝 `#409eff` 在按钮/选中/链接等主交互处**不得残留**；语义色为矿物系：success `#2f9a6c` / warning `#c4872e` / danger `#c03a2e`，无霓虹三色 |
| 品牌 token | 扩展变量可用性 | `--brand:#1e5a52`、`--brand-dark:#17483f`、`--brand-soft:#e6efed`、`--brand-deep:#102a28`、`--surface:#f8f7f3`、`--page-bg:#f6f5f1` 在需要处正确引用（Home 磁贴/识别结果卡/编号方块等） |
| 登录页 | 蜀道山黛渐变 + 品牌字 | 背景为「山黛渐变」`linear-gradient(160deg,#0a1f1e→#14342f→#1b4740)` + 两处 radial 高光；`蜀道安全助手` 标题用衬线品牌字（Songti SC/Noto Serif SC），非模板冷蓝海军渐变 |
| 侧栏 | 玄青侧栏 | 菜单背景 `--brand-deep #102a28`（玄青），文字 `#9ab0ac`、激活 `#ffffff`、hover `#1a3b38`；logo 宽字距衬线；侧栏折叠动画流畅无硬编码 props 残留 |
| 首页 | 磁贴/问候 | 问候语（按小时）用 `brand-soft` 底 + `brand` 字；模块磁贴按角色过滤正确，hover/阴影为暖调（`rgba(23,45,43,…)`） |
| AI 识别面板 | 暖纸面卡片 | `AiAnalyzePanel` 结果卡用 `--surface #f8f7f3` 暖纸面，detections 编号方块 `brand-soft` 底 + `brand` 字；`report` 文本排版清晰 |
| 全局组件一致性 | 圆角/阴影/字体 | 组件圆角 4px→6px 全局生效；页面背景 `#f6f5f1` 暖石板灰；主文字 `#232b2a`；无残留默认蓝按钮、无彩虹色块 |
| 响应式与回归 | 视觉重设计不破坏功能 | 登录→首页→隐患→问答→考试全链路跑通；窄屏下侧栏折叠、登录卡片不溢出；对比重设计前截图确认三大模块功能可用性未回归 |

### 3.6 UAT 可勾选验收表

> 勾选口径：✅ 通过 / ⚠️ 有缺陷需修复 / ❌ 未通过。本表打印随验收报告归档。

**基础支撑 B01-B03**

| 勾选 | 验收项 | 标准 |
|---|---|---|
| ☐ | B01 注册（弱口令拒绝、重复用户名 400） | 见 3.1 |
| ☐ | B01 登录（错误密码 401、禁用账号 401、JWT 120min） | 见 3.1 |
| ☐ | B02 角色矩阵（员工禁管理 403、管理员全通） | 见 3.1 |
| ☐ | B03 上传白名单 + 5MB 上限（前端预校验 + 后端 400 兜底） | 见 3.1 |

**模块一 隐患 H01-H03**

| 勾选 | 验收项 | 标准 |
|---|---|---|
| ☐ | H01 上报（编号唯一、待处理态、位置兜底、描述空 422） | 见 3.2 |
| ☐ | H01 多图 ≤9 张 | 见 3.2 |
| ☐ | H01 视觉识别（analyze→应用到表单→上报；VISION 未配置 503 降级可手动兜底） | 见 3.2 |
| ☐ | H02 五维筛选 + 排序 + 分页 | 见 3.2 |
| ☐ | H03 详情时间线 + 员工闭环 403 + 管理员闭环留痕 + 重复闭环 400 | 见 3.2 |

**模块二 AI 助手 A01-A03**

| 勾选 | 验收项 | 标准 |
|---|---|---|
| ☐ | A01 问答 SSE（meta→delta→done、citations 一致、synthetic） | 见 3.3 |
| ☐ | A01 多轮指代消解 + 拒答话术 | 见 3.3 |
| ☐ | A02 会话管理（倒序、级联删除、他人 404） | 见 3.3 |
| ☐ | A03 流式中断容错 + 敏感词 400 | 见 3.3 |

**模块三 考试工坊 E01-E05**

| 勾选 | 验收项 | 标准 |
|---|---|---|
| ☐ | E01 题库 CRUD（禁改 type、被引用禁删） | 见 3.4 |
| ☐ | E02 AI 出题（≥5 题/batch、审核流转、重写链） | 见 3.4 |
| ☐ | E03 组卷（均分、及格线≤总分、发布锁、已发布禁删） | 见 3.4 |
| ☐ | E04 在线考试（倒计时、自动保存、恢复、切屏>3 交卷、超时交卷） | 见 3.4 |
| ☐ | E05 自动阅卷（多选全对/漏选 0 分、成绩单、并发双交只评一次） | 见 3.4 |

**「青石黛」视觉重设计**

| 勾选 | 验收项 | 标准 |
|---|---|---|
| ☐ | 全局主色替换（#409eff 无残留、矿物语义色） | 见 3.5 |
| ☐ | 登录页山黛渐变 + 品牌衬线字 | 见 3.5 |
| ☐ | 侧栏玄青（#102a28 菜单、hover/激活色） | 见 3.5 |
| ☐ | 首页磁贴 + AI 识别暖纸面板（--surface/--brand-soft） | 见 3.5 |
| ☐ | 全局组件一致性（圆角 6px、暖阴影、无彩虹色） | 见 3.5 |
| ☐ | 视觉重设计后全链路功能回归 | 见 3.5 |

---

## 4. 验收结论建议

- 安全测试（§1.2 S-01~S-19）与性能测试（§2）宜自动化进 CI：安全项可并入 pytest（`test_security.py`，mock 外部依赖），性能项落地 Locust/k6 门禁（50 QPS / 首包 ≤3s / P95 ≤500ms）。
- UAT（§3）为人工验收，逐项勾选并附截图（尤其「青石黛」视觉项）；「已知缺口」清单（§1.3）随报告一并交付，避免验收误报。
- 交付物配套缺口：`docs/API.md`、根 `requirements.txt`、Dockerfile/docker-compose、pytest/vitest 载体、CI 流水线均未落地，须在测试方案排期第一节并行补齐（否则本章节无法自动执行）。

---

# 附录 A 完整性评审缺口与修订记录

完整性评审（对照 `docs/项目任务书-蜀道安全助手.md`、`docs/PRD.md` 与安全约束）共发现 12 项缺口，全部已在正文修订落实，无遗留矛盾：

| # | 缺口 | 修订位置 |
|---|---|---|
| 1 | ExamTaking / ExamResult 单测声明与前端目录树、组件表不一致 | 第三章 §2.4 补 `exam-taking.spec.ts` / `exam-result.spec.ts`；§3.3 组件表补对应行 |
| 2 | v-html 四消费点（MarkdownRenderer/QuestionCard/ExamResult/ArticleDialog）仅测了一个 | 第三章 §3.3 补 QuestionCard / ExamResult / ArticleDialog 的 XSS 注入用例 |
| 3 | 考试工坊管理端（E01-E03）前端 E2E 空白 | 第三章 §4.4 新增流 D 管理端 E2E；§5.1 V-06 截图基线纳入管理端页 |
| 4 | E02 `/ai/batches`、`/ai/batches/{id}`、`/ai/stats`、`/exams/records` 无专门用例 | 第二章 §3.5 增 G5/G6（通过率口径、空批次 0.0、本人记录分页） |
| 5 | 性能无硬门禁，验收无法判定 pass/fail | 第五章 §2 增三个关键接口最低门禁（login / hazards / chat 首包） |
| 6 | 浏览器跨核兼容（PRD §6.3）无载体 | 第三章 §4 基建增 firefox/webkit 冒烟档 |
| 7 | 前端首屏测量无工具、无口径（"计划写得到、执行不了"） | 第五章 §2.1 定义 Playwright performance + 预算断言 |
| 8 | `tests/perf/` 目录被引用但目录树缺失 | 第二章 §1.2 目录树补 `tests/perf/` |
| 9 | 集成层触发 lifespan 会真实加载分钟级 bge 模型 | 第二章 §1.3 明确免 lifespan（ASGITransport）+ conftest 可执行示例 |
| 10 | SSE 60s ping 契约与实际实现不符（未发 ping 帧） | 第一章 §1.2 M3 范围表 + 第四章 §4.3.7 记录现状，验收口径以实际行为为准 |
| 11 | RAG e2e 数据隔离口径冲突 | 第一章 §3.5 明确「独立 MySQL 测试库 + 真知识库只读复用」组合口径 |
| 12 | UAT 缺「AI 识别→应用到表单→上报」专项及 VISION 503 降级项 | 第五章 §3.2 / §3.6 补视觉识别验收场景与勾选项 |

**评审总评**：方案对三大模块、五级测试与青石黛视觉回归覆盖极全，盘点事实核验高度准确（SSE 无 ping、290s 超时、唯一约束、工具链缺失等约 30 项声明全部属实）。修订上述 12 项后，可作为可执行、可验收的完整测试方案。

**执行前置（各章都依赖、须先补齐的基建）**：`docs/API.md`（接口契约文档缺失，由本方案自建接口清单替代）、根 `requirements.txt`（RAG/AI 依赖清单需补回）、Docker/CI 载体、pytest/vitest/playwright 工具链（第一章 M0 里程碑）。


