# 蜀道安全助手 前端设计（FRONTEND · 收敛版）

| 项 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 日期 | 2026-08-13 |
| 状态 | 已收敛（评审 4 高 5 中 3 低全部裁决） |
| 章节来源 | `docs/frontend_design/01~05`（逐模块细规格）+ `docs/frontend_design/00-评审.md`（一致性审计） |
| 关联文档 | PRD.md §2/§3/§5、ARCHITECTURE.md §4、DATABASE.md |

> 本文是**唯一真源**：路由、meta 约定、目录命名、请求封装、SSE、角色守卫、后端配套改动均以此为准。各模块页面级细规格见对应章节文件，与本文冲突处**以本文为准**。

---

## 0. 全局裁决（评审 C1–C10 / R1 的收敛决定）

| 评审项 | 决定 |
| --- | --- |
| C1 路由冲突 | 以本文 §3 路由表为唯一真源（考试端用 recordId 锚点、管理端 `/exam/...`、隐患 `/hazards/*`、AI `/ai/assistant`） |
| C2 meta.roles 类型 | 全站统一 **`meta.roles: number[]`（`[2,3]`）**，守卫 `!roles.includes(role_id)`；删除字符串写法 |
| C3 成绩单数据源 | **后端新增 `GET /api/v1/exams/records`**（本人考试记录分页列表）+ 前端 `/exams/records` 页（见 §7.2 后端配套），菜单「考试记录」落地有数据 |
| C4 默认落地页 | 登录后 → **`/home`**（首页三模块入口卡片）；`/` redirect `/home`；角色拦截也回 `/home` |
| C5 目录/命名 | 统一 `src/store/`（非 stores）、`src/api/request.ts`（+ `auth/hazard/ai/exam.ts`）、单一布局 `src/layout/index.vue` |
| C6 解包策略 | 普通接口走 `request`（解包回 `data`）；`/hazards/upload`、`/hazards/analyze` 走 `uploadRequest`（返回原样 `ApiResponse`，调用方判 `code`） |
| C7 Markdown | **`marked` + `DOMPurify`**，统一在 `src/utils/markdown.ts`（模块二章节详细），禁用 markdown-it |
| C8 时长禁改 | `status==PUBLISHED` 且存在进行中考试时 duration 禁改（草稿期可改） |
| C9 批量审核 | 批量通过/驳回对话框加 `interference_verified` 勾选一并传入 |
| C10 提示文案 | `request.ts` 统一导出 `NOT_FOUND_MSG='请求的资源不存在'`、`FORBIDDEN_MSG='无权限访问该接口'` |
| R1 隐患排序 | **后端 `GET /hazards` 增 `sort`（create_time\|level）+ `order`（asc\|desc）参数**，列表列头可点击排序（PRD H02 验收闭环） |
| F1 公开选卷 | **后端新增 `GET /api/v1/exams/papers`**（公开、仅 PUBLISHED、脱敏无答案）——否则员工无法进入考试，阻塞 |
| F2 历史原文 | 历史消息 sources 缺 doc_id/article_no → 前端置灰；可选后端在 `list_messages` 补 `doc_id`+`article_no`（本期先置灰） |

---

## 1. 技术栈与脚手架

已确认决策：**Vue3 (Composition API) + TypeScript + Vite + Element Plus + Pinia + Vue Router 4 + Axios + marked/DOMPurify**；npm（Node 24）；`marked`+`DOMPurify` 渲染 AI 回答。

```bash
cd shudao
npm create vite@latest frontend -- --template vue-ts
cd frontend
npm i vue-router pinia element-plus @element-plus/icons-vue axios marked dompurify dayjs
npm i -D @types/node @types/marked @types/dompurify
```

tsconfig 要点：`strict: true`、`paths: {"@/*": ["src/*"]}`、`moduleResolution: "bundler"`。

vite.config.ts：dev proxy `/api`、`/uploads` → `http://127.0.0.1:8000`（changeOrigin）；build `manualChunks: { element: ['element-plus'] }`；Element Plus 全量引入 + `zhCn` locale（实训项目简化配置，不做按需）。

## 2. 目录结构（唯一真源）

```text
frontend/src/
├── main.ts / App.vue          # 装配 ElementPlus(zhCn)+pinia+router+全量图标
├── types/                     # api.d.ts(ApiResponse/PageResult) + models/{user,hazard,chat,exam}.ts
├── router/
│   ├── index.ts               # 路由表 + 守卫（唯一真源，见 §3）
│   └── menu.ts                # 侧栏菜单配置常量（按 meta.roles 过滤）
├── store/
│   ├── user.ts                # token(localStorage shudao_token)/user/role_id/login/logout/fetchMe
│   ├── app.ts                 # 侧栏折叠/高亮/面包屑
│   └── modules/               # chat.ts(流式态) hazard.ts(列表筛选) exam.ts(考试态)
├── api/
│   ├── request.ts             # request(JSON解包) + uploadRequest(原样) + 401处理 + 错误文案常量
│   ├── auth.ts / hazard.ts / ai.ts / exam.ts
├── layout/index.vue           # 左菜单+右内容（Sidebar.vue + HeaderBar.vue + router-view）
├── views/
│   ├── login/Login.vue        # P01（注册弹窗）
│   ├── home/Home.vue          # 首页三模块入口卡片（默认落地）
│   ├── hazard/{HazardReport,HazardList,HazardDetail}.vue   # P02/P03/P04
│   ├── ai/AiAssistant.vue     # P05（左会话+右对话）
│   └── exam/
│       ├── QuestionBank.vue   # P06 [2,3]
│       ├── ai/{AiGenerate,AiBatches,AiBatchDetail,AiStats}.vue  # P07 E02 [2,3]
│       ├── paper/{PaperList,PaperCreate,PaperDetail}.vue        # P08 E03 [2,3]
│       ├── ExamPicker.vue     # P09-A 选卷（/exams）
│       ├── ExamTaking.vue     # P09-B 作答（/exams/:recordId）
│       ├── ExamResult.vue     # P10 成绩单（/exams/:recordId/result）
│       └── ExamRecords.vue    # 我的考试记录（/exams/records，配套新接口）
├── components/
│   ├── common/                # PageHeader / PaginationBar / StatusTag / LevelTag
│   ├── hazard/                # HazardImageUpload / AiAnalyzePanel / HazardFilterBar / HazardTimeline
│   ├── chat/                  # ChatSidebar / MessageList / MarkdownRenderer / CitationPanel / ChatInputBar / ArticleDialog
│   └── exam/                  # QuestionFormDialog / ReviewDialog / BatchReviewBar / ExamCountdown / QuestionCard / ...
└── utils/
    ├── sse.ts                 # fetch 流分帧（meta/delta/ping/done + AbortController）
    ├── markdown.ts            # marked → DOMPurify → [n] 上标（唯一净化管线）
    ├── validate.ts            # 图片 ≤5MB jpg/png/jpeg 预校验
    ├── format.ts              # 日期/枚举文案/角色名
    └── constants/             # hazard.ts(等级/状态) question.ts(题型/难度/状态) paper.ts(状态/时长) —— 枚举唯一真源
```

## 3. 路由表与守卫（唯一真源）

### 3.1 路由表

`meta` 约定：`{ title, public?, roles?: number[], hidden?, menu?: 'hazard'|'ai'|'exam'|'none' }`。

| 路径 | name | 页面 | meta.roles | hidden | 说明 |
| --- | --- | --- | --- | --- | --- |
| `/login` | Login | P01 登录/注册 | — | | `public: true` |
| `/` | — | redirect `/home` | | | |
| `/home` | Home | 首页入口卡片 | | | 默认落地 |
| `/hazards` | HazardList | P03 隐患列表 | | | 模块一菜单 |
| `/hazards/report` | HazardReport | P02 隐患上报 | | | |
| `/hazards/:id` | HazardDetail | P04 隐患详情 | | ✅ | |
| `/ai/assistant` | AiAssistant | P05 AI 助手 | | | 模块二菜单 |
| `/exam/questions` | QuestionBank | P06 题库管理 | [2,3] | | 考试工坊·管理 |
| `/exam/ai/generate` | AiGenerate | E02 生成题目 | [2,3] | | 子菜单 |
| `/exam/ai/batches` | AiBatches | E02 批次审核 | [2,3] | | 子菜单 |
| `/exam/ai/batches/:batchId` | AiBatchDetail | E02 批次详情 | [2,3] | ✅ | |
| `/exam/ai/stats` | AiStats | E02 出题统计 | [2,3] | | 子菜单 |
| `/exam/papers` | PaperList | P08 试卷管理 | [2,3] | | |
| `/exam/papers/create` | PaperCreate | 组卷(manual/auto) | [2,3] | ✅ | `?mode=manual\|auto` |
| `/exam/papers/:pid` | PaperDetail | 试卷详情 | [2,3] | ✅ | |
| `/exams` | ExamPicker | P09-A 选卷 | | | 考试中心菜单 |
| `/exams/:recordId` | ExamTaking | P09-B 作答 | | ✅ | 刷新恢复锚点 |
| `/exams/:recordId/result` | ExamResult | P10 成绩单 | | ✅ | |
| `/exams/records` | ExamRecords | 我的考试记录 | | | 配套新接口 |
| `/:pathMatch(.*)*` | NotFound | 404 | | ✅ | |

### 3.2 守卫（router.beforeEach）

1. `to.meta.public`（/login）：已登录 → 回 `/home`；否则放行。
2. 无 token → `/login?redirect=<to.fullPath>`。
3. 有 token 无 user（刷新场景）→ `await fetchMe()`；失败（401）→ 清 token 回 `/login`。
4. `to.meta.roles && !roles.includes(user.role_id)` → `ElMessage.warning('无权访问该页面')` + 回 `/home`。
5. 设 `document.title`；返回 true。

### 3.3 角色口径

`role_id`：1=EMPLOYEE 普通员工、2=SAFETY 安全管理员、3=ADMIN 系统管理员。管理页（题库/AI出题/组卷）`[2,3]`；隐患闭环按钮 `[2,3]`；其余需登录即可。后端 `require_roles` 为硬门禁，前端 meta.roles 仅 UX（菜单隐藏 + 路由拦截）。

## 4. 请求层与错误处理（src/api/request.ts）

- 单实例 `axios.create({ baseURL: '/api/v1', timeout: 15000 })`；请求拦截注入 `Authorization: Bearer <token>`（读 localStorage `shudao_token`）。
- 响应拦截：401 → `onUnauthorized()`（清 token + 防重复跳 `/login`，带 redirect）。
- **`request<T>(config): Promise<T>`**：解包 `{code,message,data}`；`code!==200` 抛 `ApiError(code,message)` 并 `ElMessage.error`；HTTP 层错误（403/404/422/502/503/网络）统一提示。
- **`uploadRequest<T>(config): Promise<ApiResponse<T>>`**：不做 JSON 解包，返回原样 body，调用方判 `code`（上传/AI 识别专用，业务失败要拿 503 降级信息）。
- 超时特例：analyze `timeout: 160_000`（后端 150s 上限+余量）、upload `30_000`。
- 文案常量：`NOT_FOUND_MSG='请求的资源不存在'`、`FORBIDDEN_MSG='无权限访问该接口'`；503 视觉「视觉识别不可用，可跳过或稍后重试」；502「AI 服务异常，请稍后重试」。

## 5. SSE 客户端（src/utils/sse.ts）

- **用 fetch 而非 EventSource**：`/chat` 需 `Authorization` 头，EventSource 无法携带。
- `chatSSE(body, {onMeta,onDelta,onDone,onError}, signal?)`：POST `/api/v1/ai/chat`；非 2xx → 解析 `{code,message}` 走 onError；2xx → `reader.read()` 按 `\n\n` 分帧，解析 `event:`/`data:`，`ping` 忽略。
- 事件序 `meta → delta* → done`（契约 `qa_service._sse`）：meta `{conversation_id,user_message_id,mode,confidence,citations,rewritten_used}`；delta `{text}`；done `{answer_id,citations,grounding_score,synthetic,error?}`。

## 6. 页面规格（模块章节引用）

| 页面 | 核心要点 | 细规格 |
| --- | --- | --- |
| P01 登录/注册 | 表单编码登录（`URLSearchParams`，**非 JSON**）；注册成功回填登录不自动登录；登录响应自带 `user` | 02 §3 |
| P02 隐患上报 | 描述/等级必填 + 位置/类型可选 + 多图（≤9，先 /upload 拿 URL）；**AI 识别增强**：analyze → 回显 type/level/description/reason/confidence + detections 编号配色 + 多框标注图；`report` 整体回传 `risk_report`；503 降级可手动 | 02 §4 |
| P03 隐患列表 | 筛选（status/level/type/keyword/时间区间）+ 分页 + **列头排序（sort/order 新参数）** | 02 §5 |
| P04 隐患详情 | 全字段 + 图片缩略图 + el-timeline + 闭环按钮（[2,3] & WAIT_PROCESS 双门控） | 02 §6 |
| P05 AI 助手 | 左 280px 会话 + 右对话；SSE 流式（meta 先渲染引用）；marked+DOMPurify+`[n]` 上标；快捷提问/点赞点踩/查看原文；历史消息原文置灰 | 03 |
| P06 题库管理 | 筛选+分页 CRUD；按题型动态表单（单选/多选/判断/填空）；解析必填；编辑禁改 type | 04 §2 |
| P07 AI 出题 | 生成参数表单 + 生成中态；批次列表（通过率进度条 ≥80% success）；逐题审核/批量审核（含 interference_verified）/AI 重写；统计 | 04 §3 |
| P08 组卷 | 手动（勾选 APPROVED + 分值全指定/全均分）/智能（rules 抽题 + warnings 提示）；详情预览含答案；PUBLISHED 锁总分/及格线 | 04 §4 |
| P09 考试 | 选卷 `/exams`（公开接口）→ 作答 `/exams/:recordId`；倒计时以 `remaining_seconds` 权威；15s+切题自动保存；防切屏（>3 次自动交卷）；`state==='SUBMITTED'` 判终态 | 05 |
| P10 成绩单 | 交卷响应直接渲染；总分/合格/passed/reason + 逐题作答 vs 答案 + 解析；只展示后端已算分 | 05 |
| 考试记录 | `/exams/records` 我的记录列表（分页），点进成绩单 | 07.2 |

## 7. 配套后端改动（前端依赖，按优先级）

| 优先级 | 改动 | 说明 |
| --- | --- | --- |
| **P0 阻塞** | 新增 `GET /api/v1/exams/papers`（公开，仅 PUBLISHED，脱敏：id/name/total_score/pass_score/duration/question_count，无题目答案） | 员工无法选卷，考试链路断 |
| P1 | 新增 `GET /api/v1/exams/records`（当前用户考试记录分页：record_id/paper_name/status/score/passed/submitted_at） | 「考试记录」菜单数据源 |
| P1 | `GET /api/v1/hazards` 增 `sort`(`create_time`\|`level`) + `order`(`asc`\|`desc`)，默认 create_time desc | PRD H02 排序验收 |
| P2 | （可选）`list_messages`/`get_sources` 的 source 补 `doc_id`+`article_no`，使历史消息可查看原文 | 不阻塞，先置灰 |
| P2 | （可选）`QuestionOut.reviewer` 补 `reviewer_name` 展示姓名 | 不阻塞，先显示 id |
| P2 | （可选）`/ai/stats` 补 `by_type`/`by_difficulty` 分布 | 统计页分布图后置 |

## 8. 实施顺序（按 PRD 顺序全量）

1. **脚手架 + 地基**：Vite+TS 初始化、依赖、目录、request.ts、sse.ts、store、router+守卫、layout、P01 登录注册、P03 列表骨架。
2. **模块一 隐患**：P02 上报（含 AI 识别回显 + 多框标注图）、P03 列表（含排序）、P04 详情（时间线/闭环）。
3. **模块二 AI 助手**：P05 会话列表 + SSE 流式 + 引用/反馈/快捷提问。
4. **模块三 考试工坊**：管理端（P06 题库 / P07 出题 / P08 组卷）→ 考试端（P09 选卷/作答 / P10 成绩单 / 考试记录）。
5. **联调 + 后端配套**：实现 §7 后端改动，逐页联调验证。

## 9. 非功能

- **安全**：AI 文本一律 `marked→DOMPurify→v-html`；普通文本用 `{{ }}` 自动转义；上传双端校验（前端 beforeUpload + 后端 400 兜底）；token localStorage + 401 统一登出。
- **性能**：路由懒加载 + element 独立 chunk；服务端分页；`el-image` 懒加载。
- **兼容**：Chrome/Edge/Firefox/Safari 近 2 大版本；Node 18+ 构建（本机 Node 24）。
