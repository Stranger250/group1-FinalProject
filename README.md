# 蜀道安全助手（ShuDao Safety Assistant）

面向交通基建企业的安全生产培训管理系统：**在线考试工坊 + AI 法规问答（RAG）+ 隐患排查闭环**。

- 后端：Python 3.12 / FastAPI / SQLAlchemy / MySQL / Chroma / Redis
- 前端：Vue 3 / TypeScript / Vite / Element Plus / Pinia
- AI：DeepSeek LLM、bge-large-zh 嵌入、bge-reranker 精排、BM25(jieba)、阿里云视觉
- 部署：Docker Compose（后端 :8002 / 前端 nginx :8080）

---

## 功能总览

| 模块 | 能力 |
| --- | --- |
| **隐患管理** | 三级分类树（6 大类 36 子类）、图片上传 + AI 视觉识别 + 勾选保留、三段式上报、派单/整改/验收闭环、安全员处理、数据隔离（普通用户仅本人可见，404 掩码） |
| **AI 智能助手** | SSE 流式问答、混合检索引用溯源（可点击查看原文）、回答依据按国家级/省级/更低级分层、快捷提问、反馈、对话内文件上传（txt/md/pdf/docx 解析注入上下文） |
| **考试工坊** | 五题型全链路：用户提交题目 → 管理员审核 → 自由组卷 → 发布考试给指定用户（昵称搜索/多选/可撤销）→ 在线作答 → 自动阅卷 → 统计与错题本；Word 导出（仅题目/含答案） |
| **法规文档库** | 全量浏览（类型/层级/关键字筛选、分页、条数字数统计）、正文分章预览；管理端上传 txt/md/pdf/docx 即入库（复用建库管道增量构建）、停用/启用/删除即时生效 |
| **管理配置** | 模型配置（LLM/视觉，api_key 脱敏回显、写配置存储即时生效）、RAG 检索/分块参数管理（分块变更提示重建） |
| **AI 文档生成** | DeepSeek 生成结构化大纲 → python-docx / python-pptx 本地渲染 Word / PPT（≥8 页，含封面/目录/结束页）→ 下载；敏感词检查 + 审计留痕 |
| **日志与审计** | 关键操作审计全覆盖；日志上报预留接口（OA 对接，未配置地址不发外部请求） |

## RAG 架构

```
查询 → ①向量路（bge-large-zh, top50）
      → ②BM25 路（jieba, top50）        → ③RRF K60 融合 top20
      → ④交叉引用展开（第X条 → 被引条）
      → ⑤bge-reranker 精排 Top5
      → ⑥置信度分级（refuse / conservative / full，低相似度拒答防幻觉）
      → LLM（DeepSeek）SSE 流式回答 + 引用溯源
```

- **知识库**：98 篇真实公开文档 / 16261 条法规条文 / 7171 分块（六类：法律 9 / 法规 19 / 企业制度 5 / 操作规程 3 / 预案 12 / 案例 50），**全部来自官方公开渠道爬取（应急管理部事故调查报告、政府应急预案、企业公开制度等），零编造数据**；MySQL 与 Chroma 双写一致
- **评测**：100 条评测集（50 单块 / 33 双块 / 17 三块，`backend/data/eval/queries_v2.json`），一键脚本输出 Recall@5 / MRR / NDCG
- **优化记录**：单变量对照实验（每次只改一个参数，效果更好才采纳）——通过评测集校准（42 处标注修正）与语料去重（删除 3 组重复文档），Recall@5 从 0.825 提升至 0.897；实体名检索优化（标题路 BM25 + rerank 标题注入）持续迭代中，目标 ≥0.92

## 快速开始

### 前置

- Docker + Docker Compose
- 宿主机 MySQL 8（`shudao` 库）与 Redis（容器经 `host.docker.internal` 复用）
- 本地模型目录：bge-large-zh、bge-reranker-base（路径经环境变量注入）
- LLM / 视觉 API Key：复制 `backend/.env.example` 为 `backend/.env` 后填写

### 启动

```bash
# 1) 初始化数据库（幂等：建表 + 种子数据 + 迁移）
cd backend && python scripts/init_db.py

# 2) 构建知识库（首次需要；语料在 crawler_output/，约 1.5h CPU）
cd backend && python scripts/build_knowledge_base.py --force

# 3) 容器部署
docker compose -f backend/docker-compose.yml up -d --build

# 4) 访问
#    前端 http://localhost:8080 （管理员 admin / Admin@123456，请尽快修改）
#    后端 API http://localhost:8002/docs
```

### 常用命令

```bash
# RAG 评测（单变量实验：--set 覆盖参数、--tag 标记存档）
cd backend && python scripts/eval_rag.py --queries data/eval/queries_v2.json --save data/eval/out.json --set rag_rrf_k=40 --tag exp-xxx

# 回归测试（BASE_URL 指向后端）
cd backend && $env:BASE_URL='http://127.0.0.1:8002/api/v1'; python scripts/test_bugfix.py

# 爬虫（语料扩充，幂等可重跑）
cd backend && python scripts/crawler_mem_bulk.py
```

## 目录结构

```
backend/
  app/                # FastAPI 应用
    api/              # 路由层（auth/exam/hazard/chat/document/admin_config/gen_doc/log）
    service/          # 业务服务层（含 RAG 检索/文档生成/考试阅卷等）
    rag/              # RAG 核心（混合检索/BM25/精排/知识库构建管道）
    model/ schema/    # ORM 与 Pydantic 模型
  scripts/            # 爬虫 / 建库 / 评测 / 17 套回归测试
  data/eval/          # 评测集与基线存档
  Dockerfile  docker-compose.yml
frontend/
  src/                # Vue3 前端（views/components/store/api/router）
crawler_output/       # 真实语料 JSON（101 篇，建库输入）
```
