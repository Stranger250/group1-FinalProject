# 蜀道安全助手系统架构设计（ARCHITECTURE）

| 项目 | 内容 |
| --- | --- |
| 文档名称 | 蜀道安全助手系统架构设计 |
| 文档版本 | V1.0 |
| 编写日期 | 2026-08-12 |
| 文档状态 | 设计稿 |
| 关联文档 | PRD.md（产品需求）、DATABASE.md（数据库设计）、AI_SOLUTION.md（AI 技术方案） |

---

# 1. 架构目标与设计原则

## 1.1 架构目标

1. 支撑 PRD 定义的三大核心模块：隐患安全管理、AI 智能助手、考试工坊。
2. 满足企业级 Web 应用要求：稳定、安全、可扩展、可维护。
3. 支撑 AI 能力（RAG 问答、AI 出题；隐患图片识别为 V2 扩展）独立演进与扩展。

## 1.2 设计原则

| 原则 | 说明 |
| --- | --- |
| 前后端分离 | Vue3 前端与 FastAPI 后端通过 RESTful API + SSE 交互 |
| AI 服务独立化 | AI 能力封装为独立服务（ai_service），不与业务接口耦合 |
| 分层架构 | Controller → Service → Repository 职责单一、便于测试 |
| 数据隔离 | 业务数据（MySQL）、缓存（Redis）、知识数据（向量库）职责分离 |
| 审计追踪 | 隐患处理、登录等关键操作全程留痕 |
| 可扩展 | 模块化设计，为 V2.0 视频监控、语音助手预留扩展点 |

---

# 2. 系统总体架构

## 2.1 总体架构图

```text
用户
  ↓
Web 浏览器
  ↓
Vue3 前端（Element Plus / Pinia / Axios / SSE）
  ↓
FastAPI 后端（api → service → repository）
  ├── MySQL（业务数据：用户/隐患/会话/考试）
  ├── Redis（缓存：登录态/热点问题/AI 上下文）
  └── AI 服务（ai_service）
        ├── LangChain（RAG Chain / 出题 Chain）
        ├── 大模型服务（Qwen / DeepSeek / GPT）
        ├── Embedding 模型（BGE）
        ├── 向量数据库（Chroma 开发 / Milvus 生产）
        ├── Reranker（bge-reranker）
        └── 视觉模型（千问 qwen-vl，V2 预留）
```

## 2.2 分层职责

| 层 | 职责 | 技术载体 |
| --- | --- | --- |
| 展示层 | 页面渲染、用户交互、流式展示 | Vue3 + Element Plus |
| 接入层 | RESTful API、SSE、参数校验、鉴权 | FastAPI |
| 业务层 | 隐患闭环、会话管理、考试流程等业务逻辑 | FastAPI Service |
| AI 能力层 | RAG 检索生成、AI 出题、图片识别（V2） | ai_service（LangChain） |
| 数据层 | 业务数据、缓存、向量、文件存储 | MySQL / Redis / Chroma·Milvus / 对象存储 |

---

# 3. 技术选型总览

| 模块 | 技术 | 选型理由 |
| --- | --- | --- |
| 前端 | Vue3 + TypeScript | 组合式 API、类型安全、社区成熟 |
| UI | Element Plus | 企业后台组件齐全，中文生态好 |
| 状态管理 | Pinia | Vue3 官方推荐，轻量 |
| 网络请求 | Axios | 拦截器便于统一鉴权与错误处理 |
| 实时通信 | SSE | 单向流式推送，天然适配 AI 生成 |
| 后端 | FastAPI | 异步高性能、自动 OpenAPI 文档、与 Python AI 生态无缝衔接 |
| 数据库 | MySQL 8.x | 关系型业务数据存储 |
| 缓存 | Redis | 登录态、热点问题、AI 临时上下文 |
| AI 框架 | LangChain | RAG、Chain、Prompt 管理标准方案 |
| 向量库 | Chroma（开发）/ Milvus（生产） | 开发轻量，生产可扩展 |
| Embedding | BGE / text-embedding | 中文效果好 |
| Reranker | bge-reranker | 精排提升召回质量 |
| LLM | Qwen / DeepSeek / GPT | 国内大模型 API 合规、成本可控，支持流式 |
| 视觉识别（V2） | 千问视觉大模型（qwen-vl） | 目标检测 + 场景理解 |
| 部署 | Docker + Nginx | 容器化、统一入口、便于扩展 |

### 3.1 后端选型说明（2026-08-12 决策：全 FastAPI，取代任务书 Spring Boot）

> 任务书 §1.3 原定后端为 Spring Boot 3.x + MyBatis Plus。**本方案以 `docs/PRD.md` v1.0.1 为唯一需求参照，PRD §2 明确后端为 Python/FastAPI**，故弃用 Spring Boot。取舍依据：

| 对比维度 | FastAPI（采用） | Spring Boot（任务书原定，已弃） |
| --- | --- | --- |
| 需求依据 | PRD §2 原文（唯一参照） | 任务书 §1.3（已被 PRD 取代） |
| AI/RAG 生态 | LangChain、bge-large-zh、Chroma、jieba、sse 全为 Python 原生，业务后端与 RAG **同栈**，无跨语言桥 | Java 侧无法直接调用，须另保留 Python rag-service，多一套跨语言 HTTP + SSE 转发 |
| SSE 流式 | `StreamingResponse` 原生逐事件 yield（meta→delta→done） | 需 `WebClient` 转发 Python 侧 SSE，多一跳延迟与故障点 |
| 开发成本 | 单语言单代码库，实训 1-2 人可覆盖 | 双语言双代码库，工作量约翻倍 |
| 一致性 | 全栈一套 API、一套鉴权/日志/权限 | 两套后端需约定内部契约，易漂移 |

**结论**：业务后端与 RAG 统一为 FastAPI 单栈，架构图简化为「Nginx → FastAPI 业务后端（含 rag 模块）」。RAG 优化方案 §6 与此一致（SSE 由后端原生实现，见其 §6.6）。任务书 Spring Boot 仅作历史背景保留，不参与本期实现。

---

# 4. 前端架构

## 4.1 技术栈

| 项 | 技术 |
| --- | --- |
| 框架 | Vue3（Composition API） |
| 语言 | TypeScript |
| 构建工具 | Vite |
| UI 组件 | Element Plus |
| 状态管理 | Pinia |
| 路由 | Vue Router |
| 网络请求 | Axios |
| 实时通信 | EventSource / fetch stream（SSE） |

## 4.2 目录结构

```text
frontend/
├── index.html
├── vite.config.ts
├── package.json
└── src/
    ├── main.ts
    ├── App.vue
    ├── router/
    │   └── index.ts
    ├── api/
    │   ├── request.ts          # Axios 封装：token 注入、统一错误处理
    │   ├── auth.ts
    │   ├── ai.ts
    │   ├── hazard.ts
    │   └── exam.ts
    ├── store/
    │   ├── user.ts
    │   └── chat.ts
    ├── views/
    │   ├── Login.vue
    │   ├── Home.vue
    │   ├── AIChat.vue
    │   ├── Hazard.vue
    │   └── Exam.vue
    ├── components/
    │   ├── ChatBox.vue
    │   ├── HistoryList.vue
    │   ├── HazardCard.vue
    │   ├── HazardTimeline.vue
    │   ├── ImageAnalyzer.vue
    │   └── ExamPreview.vue
    └── utils/
        └── sse.ts              # SSE 客户端封装
```

## 4.3 路由规划

| 路径 | 页面 | 说明 |
| --- | --- | --- |
| /login | 登录页 | 登录与权限校验 |
| / | 首页 | 系统统一入口 |
| /ai | AI 智能助手 | 左历史会话 + 右聊天区 |
| /hazard | 隐患管理 | 图片检测、上报、列表、详情 |
| /exam | 考试工坊 | 出题、组卷、考试、成绩 |

## 4.4 关键设计

- **Axios 拦截器**：请求头注入 `Authorization: Bearer <token>`；响应统一处理 `code/message/data` 结构；401 自动跳转登录。
- **SSE 接入**：`/api/v1/ai/chat` 使用 fetch stream 或 EventSource 逐 token 渲染；AI 回答支持 Markdown 渲染与引用来源折叠展示。
- **权限控制**：路由守卫根据用户角色（普通员工/安全管理员/系统管理员）控制页面与按钮可见性。

---

# 5. 后端架构

## 5.1 分层设计

| 层 | 职责 | 目录 |
| --- | --- | --- |
| API 层 | 接收请求、参数校验、返回结果、SSE 流 | app/api/ |
| Service 层 | 业务逻辑编排（隐患闭环、RAG 调用、出题流程） | app/service/ |
| Repository 层 | 数据库读写 | app/repository/ |
| Model 层 | ORM 数据模型 | app/model/ |
| Schema 层 | Pydantic 请求/响应模型 | app/schema/ |
| 公共层 | 鉴权、日志、配置、工具 | app/core/、app/utils/ |

## 5.2 目录结构

```text
backend/
├── app/
│   ├── main.py                 # FastAPI 入口、路由注册、中间件
│   ├── core/
│   │   ├── config.py           # pydantic-settings 配置
│   │   ├── security.py         # JWT、密码哈希、权限依赖
│   │   └── logging.py          # 结构化日志
│   ├── api/
│   │   ├── auth.py             # POST /api/v1/auth/login
│   │   ├── ai.py               # 会话创建/列表/chat(SSE)/source
│   │   ├── hazard.py           # 隐患 create/list/detail/status/image.analyze
│   │   └── exam.py             # 出题 generate/create/list/submit
│   ├── service/
│   │   ├── auth_service.py
│   │   ├── ai_service.py
│   │   ├── hazard_service.py
│   │   └── exam_service.py
│   ├── repository/
│   │   ├── user_repo.py
│   │   ├── conversation_repo.py
│   │   ├── hazard_repo.py
│   │   └── exam_repo.py
│   ├── model/                  # SQLAlchemy 模型（对应 DATABASE.md）
│   ├── schema/                 # Pydantic 模型
│   └── utils/
│       ├── response.py         # 统一返回结构
│       └── sse.py              # SSE 事件封装
├── alembic/                    # 数据库迁移
├── requirements.txt
└── .env.example
```

## 5.3 统一响应与异常处理

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

- 业务异常统一抛出，由全局异常处理器转换为统一结构。
- 参数校验由 Pydantic 完成，校验失败返回 400。
- 未登录/无权限返回 401/403。

## 5.4 鉴权设计

- 登录接口校验用户名密码（bcrypt 哈希），签发 JWT（有效期建议 2 小时，Redis 可存续期）。
- RBAC 权限：`role` 表定义角色，接口依赖注入校验角色权限：
  - 普通员工：隐患上报、AI 问答、参加考试。
  - 安全管理员：隐患派单、验收、题目审核、统计分析。
  - 系统管理员：用户管理、权限管理、系统配置。
- 关键操作（派单、验收、登录）写入审计日志。

---

# 6. AI 服务架构

## 6.1 服务定位

AI 能力独立封装为 `ai_service`，与 FastAPI 业务服务通过内部 HTTP 接口交互；开发阶段也可作为后端内模块（依赖注入）快速联调，生产环境独立部署，便于扩缩容。

## 6.2 AI 服务结构

```text
ai_service/
├── main.py                     # 内部服务入口
├── api/
│   ├── chat.py                 # RAG 问答（SSE）
│   ├── exam.py                 # AI 出题
│   └── vision.py               # 图片识别（V2 预留）
├── embeddings/embedding.py     # Embedding 封装
├── vectorstore/chroma.py       # 向量库封装（Chroma/Milvus 适配）
├── retriever/search.py         # 检索（向量 + 关键词混合）
├── reranker/rerank.py          # 精排
├── chains/
│   ├── qa_chain.py             # RAG 问答链
│   └── exam_chain.py           # 出题链
├── prompt/
│   ├── qa_prompt.py
│   └── exam_prompt.py
├── models/llm.py               # 大模型适配（Qwen/DeepSeek/GPT）
├── config.py
└── requirements.txt
```

## 6.3 内部服务接口

| 方法 | 内部接口 | 说明 |
| --- | --- | --- |
| POST | /internal/ai/chat | RAG 问答，SSE 流式返回 |
| POST | /internal/ai/embed | 文本向量化 |
| POST | /internal/exam/generate | AI 生成题目（JSON） |
| POST | /internal/vision/analyze | 图片隐患识别（V2 预留） |

---

# 7. 数据存储架构

| 存储 | 数据 | 说明 |
| --- | --- | --- |
| MySQL | 用户、角色、隐患、隐患日志、会话、消息、引用来源、知识文档/切片索引、题库、试卷、考试记录 | 业务事实数据 |
| Redis | 登录态、热点问答缓存、AI 临时上下文、任务状态 | 高性能读写 |
| 向量库 | 知识切片向量 | AI 检索 |
| 文件存储 | 隐患图片、知识文档原文件 | 本地目录或对象存储 |

Redis 缓存 Key 设计示例：

```text
auth:token:{jti}                 # 登录会话
cache:hot_qa:{question_hash}     # 热点问题缓存
ai:context:{conversation_id}     # AI 多轮上下文
hazard:task:{hazard_id}          # 任务状态
```

---

# 8. 核心业务调用链

## 8.1 AI 助手调用链

```text
用户输入问题
  ↓
Vue 聊天页面
  ↓
POST /api/v1/ai/chat（SSE）
  ↓
FastAPI → ai_service
  ↓
读取历史消息（MySQL）
  ↓
问题 Embedding
  ↓
向量库检索（召回 top-k）
  ↓
Reranker 精排（取 top-n）
  ↓
Prompt 组装（角色 + 资料 + 历史 + 问题）
  ↓
LLM 生成（流式）
  ↓
SSE 返回前端实时展示
  ↓
保存消息与引用来源（MySQL）
```

## 8.2 考试工坊调用链

```text
管理员输入知识点/上传资料
  ↓
POST /api/v1/exam/generate
  ↓
文档解析 → 知识库检索 → Prompt → LLM 生成题目
  ↓
JSON 解析与校验
  ↓
管理员审核
  ↓
保存题库（MySQL）
  ↓
组卷（手动/AI）生成试卷
  ↓
员工在线考试 → 提交 → 自动阅卷 → 成绩
```

## 8.3 隐患管理调用链

```text
用户上传现场图片
  ↓
POST /api/v1/hazard/image/analyze
  ↓
视觉模型（千问 qwen-vl，V2 预留）
  ↓
生成风险报告（标签/置信度/整改建议）
  ↓
用户补充信息 → 创建隐患
  ↓
安全管理员派单 → 责任人整改 → 提交反馈 → 验收闭环
  ↓
hazard_log 全程留痕
```

---

# 9. 部署架构

## 9.1 开发环境

```text
Docker Compose
├── mysql       # 业务数据库
├── redis       # 缓存
├── chroma      # 向量库（开发）
├── backend     # FastAPI
├── ai_service  # AI 服务
├── frontend    # Vite dev / build
└── nginx       # 反向代理
```

## 9.2 生产环境

```text
Nginx（统一入口、静态资源、HTTPS）
  ├── Vue 静态资源（frontend/dist）
  └── FastAPI（backend，多实例负载均衡）
        ├── MySQL（主从可选）
        ├── Redis（哨兵/集群可选）
        └── AI 服务（GPU 服务器，Milvus + 模型推理）
```

## 9.3 环境配置

| 配置项 | 说明 |
| --- | --- |
| DATABASE_URL | MySQL 连接串 |
| REDIS_URL | Redis 连接串 |
| VECTOR_DB_URL | 向量库地址（chroma/milvus） |
| LLM_API_KEY / LLM_BASE_URL | 大模型 API 密钥与网关 |
| EMBEDDING_MODEL / RERANK_MODEL | 模型名称 |
| JWT_SECRET / JWT_EXPIRE | 鉴权密钥与有效期 |
| UPLOAD_DIR / MAX_UPLOAD_SIZE | 上传目录与大小限制 |

---

# 10. 安全架构

| 维度 | 措施 |
| --- | --- |
| 认证 | JWT + 登录态缓存，密码 bcrypt 加密存储 |
| 授权 | RBAC 角色权限，接口级鉴权 |
| 传输 | HTTPS 全链路 |
| 数据 | 用户数据隔离，聊天记录权限控制，企业文档不可泄露 |
| 文件 | 类型/大小限制、白名单、恶意文件拦截 |
| 审计 | 登录、派单、验收、删除等关键操作日志 |
| AI 安全 | 回答强制引用知识库、拒绝编造、敏感词过滤 |

---

# 11. 可扩展性设计

1. **服务拆分演进**：V2.0 视频监控识别可独立为 `vision_service`，复用 ai_service 的模型管理。
2. **异步化**：AI 出题、文档解析等耗时任务可引入消息队列（Celery/RabbitMQ）异步执行。
3. **监控告警**：接入 Prometheus + Grafana，监控接口耗时、AI 调用量、错误率。
4. **水平扩展**：FastAPI 无状态化（JWT），可多实例部署；向量库使用 Milvus 支撑大数据量。

---

> 本架构文档与 PRD.md、DATABASE.md、AI_SOLUTION.md 配套使用，是后端、前端、AI 服务开发的工程蓝图。
