# 蜀道安全助手 AI 技术方案（AI_SOLUTION）

| 项目 | 内容 |
| --- | --- |
| 文档名称 | 蜀道安全助手 AI 技术方案 |
| 文档版本 | V1.0 |
| 编写日期 | 2026-08-12 |
| 文档状态 | 设计稿 |
| 关联文档 | PRD.md（产品需求）、ARCHITECTURE.md（系统架构）、DATABASE.md（数据库设计） |

---

# 1. AI 能力总览

| 能力 | 输入 | 输出 | 核心技术 |
| --- | --- | --- | --- |
| AI 智能问答 | 自然语言问题（支持多轮） | 基于知识库的回答 + 引用来源（SSE 流式） | RAG：Embedding + 向量检索 + Rerank + LLM |
| AI 智能出题 | 知识点 / 上传资料 / 题型与数量 | JSON 格式题目（题目、选项、答案、解析） | 知识库检索 + LLM 结构化生成 |
| 隐患图片识别（V2 预留） | 现场图片 | 风险标签、置信度、分析报告 | 千问视觉大模型（qwen-vl） |

---

# 2. AI 总体架构

```text
用户
  ↓
前端 Vue 交互层
  ↓
FastAPI 服务层（业务编排、会话、鉴权）
  ↓
ai_service（AI 能力层）
  ├── RAG 问答链（qa_chain）
  ├── 出题链（exam_chain）
  └── 视觉识别（vision，V2 预留）
        ↓
模型服务层
  ├── 大模型 LLM（Qwen / DeepSeek / GPT，国内大模型 API）
  ├── Embedding（BGE）
  ├── Reranker（bge-reranker）
  └── 视觉模型（千问 qwen-vl，V2 预留）
        ↓
数据层
  ├── 向量数据库（Chroma 开发 / Milvus 生产）
  ├── MySQL（知识文档/切片索引/会话/引用来源）
  └── 文件存储（原始文档、图片）
```

---

# 3. 技术选型

| 模块 | 选型 | 理由 |
| --- | --- | --- |
| AI 框架 | LangChain | 标准 RAG / Chain / Prompt 管理，生态成熟 |
| LLM | Qwen / DeepSeek（国内大模型 API，备选 GPT） | 合规、中文能力强、支持流式、成本可控 |
| Embedding | BGE / text-embedding | 中文语义效果好 |
| 向量库 | Chroma（开发）/ Milvus（生产） | 开发轻量，生产可扩展 |
| Reranker | bge-reranker | 精排提升检索准确率 |
| 流式输出 | SSE | 逐 token 推送，提升体验 |
| 视觉识别（V2） | 千问视觉大模型（qwen-vl） | 目标检测 + 场景理解 |

## 3.1 大模型选型建议

| 场景 | 建议模型 | 说明 |
| --- | --- | --- |
| 智能问答 | Qwen / DeepSeek 中档模型 | 支持流式、上下文 8K+ |
| AI 出题 | 同上 | 要求输出稳定 JSON |
| 复杂分析（可选） | GPT / 更强模型 | 按需升级 |

统一通过 OpenAI 兼容协议接入，LangChain 适配层切换模型不改业务代码。

---

# 4. RAG 智能问答方案

## 4.1 整体流程

```text
用户问题
  ↓
1. 问题预处理（多轮改写、意图判断）
  ↓
2. 问题向量化（Embedding）
  ↓
3. 向量库检索（召回 top-k=20）
  ↓
4. 关键词/BM25 检索（可选，混合召回）
  ↓
5. 合并去重
  ↓
6. Reranker 精排（取 top-n=5）
  ↓
7. Prompt 组装（角色 + 资料 + 历史对话 + 问题）
  ↓
8. LLM 生成（SSE 流式）
  ↓
9. 输出回答 + 引用来源
  ↓
10. 保存消息与引用（MySQL）
```

## 4.2 问题预处理

- 多轮对话时，先利用 LLM 或规则将当前问题结合历史改写为独立问题，再检索。
- 判断是否与安全知识相关；与知识库无关的寒暄直接走通用回复。

## 4.3 混合检索

推荐“向量检索 + 关键词检索”混合：

- 向量检索：语义匹配，召回 top-k（如 20 条）。
- 关键词检索：规范条文编号、术语精确匹配（如“第X条”）。
- 合并去重后交 Reranker 精排，取 top-n（如 5 条）进入 Prompt。

## 4.4 Reranker 精排

向量检索为粗排，通过 bge-reranker 对“问题-片段”对打分重排，选择最相关的前若干片段，减少噪声、提升准确率。

## 4.5 Prompt 设计（问答）

```text
你是一名企业安全管理专家。
请严格根据以下企业安全知识库资料回答用户问题。

【资料】
{context}

【历史对话】
{history}

【问题】
{question}

要求：
1. 回答必须基于资料，不允许编造。
2. 如果资料中没有答案，明确说明“暂无相关资料，请咨询安全管理员”。
3. 给出安全措施与操作建议。
4. 回答结尾列出引用来源（文档名称、章节、原文片段）。
```

## 4.6 引用来源

- 进入 Prompt 的每个片段记录来源（document_id、chunk_id、章节、页码）。
- LLM 回答生成后，将实际引用的片段写入 `message_source` 表。
- 前端通过 `GET /api/v1/ai/source/{message_id}` 展示“文档名称 / 章节 / 原文片段”。

## 4.7 多轮对话

- 会话与消息持久化到 MySQL（conversation / message）。
- 构建 Prompt 时取最近 N 轮（建议最近 10 条消息，约 5 轮问答），超出部分截断。
- 上下文也可临时写入 Redis（`ai:context:{conversation_id}`）提升速度。

## 4.8 SSE 流式输出

- 后端：FastAPI `StreamingResponse`，LLM 流式生成逐块 `yield`。
- 前端：`EventSource` / fetch stream 接收 `data:` 事件实时渲染 Markdown。
- 首 token 响应目标 < 3s。

## 4.9 兜底策略

| 情况 | 处理 |
| --- | --- |
| 知识库无相关内容 | 回答“暂无相关资料，请咨询安全管理员”，不编造 |
| 检索片段过少（<2 条） | 提示资料不足，建议联系管理员补充知识库 |
| 模型服务异常 | 返回友好错误，保存失败消息，允许重试 |

---

# 5. 知识库构建与管理

## 5.1 支持格式

`pdf`、`docx`、`txt`、`ppt`（解析工具：PyMuPDF、python-docx、python-pptx 等）。

## 5.2 构建流程

```text
文档上传
  ↓
文本解析
  ↓
文本清洗（去页眉页脚、乱码、空行、表格转文本）
  ↓
结构化切片（按标题/章节优先）
  ↓
Embedding 向量化
  ↓
写入向量库 + 保存 knowledge_document / knowledge_chunk 索引
  ↓
文档状态置为 SUCCESS
```

## 5.3 切片策略

| 参数 | 建议值 | 说明 |
| --- | --- | --- |
| 切片长度 | 500 ~ 1000 tokens | 保证语义完整 |
| 重叠 | 100 ~ 200 tokens | 保证上下文衔接 |
| 切分依据 | 标题/章节优先，其次按段落 | 结构化切片 |
| 元数据 | 文档 ID、章节、页码、序号 | 用于引用与溯源 |

## 5.4 知识库更新

- 新增文档：全量入库。
- 文档更新：删除旧切片与向量，重新解析入库。
- 文档删除：同步删除向量与索引，保证引用来源可追溯、无孤儿数据。

---

# 6. 考试工坊 AI 方案

## 6.1 出题流程

```text
管理员输入知识点 / 上传资料
  ↓
知识库检索（获取相关规范）
  ↓
Prompt 构造（角色 + 知识 + 题型数量难度）
  ↓
LLM 生成题目（要求输出 JSON，含来源溯源 sources）
  ↓
JSON 解析 + Pydantic 校验
  ↓
去重与完整性检查（题目、选项、答案、解析）
  ↓
暂存题库草稿（question 表，source=ai，status=PENDING，同 batch_id 一批）
  ↓
管理员审核（直接通过 / 文案润色后通过 / 驳回）
  ↓
审核通过批量入库（status=APPROVED，reviewer、review_note、interference_verified 落库）
```

> **重写增强（方案B）**：被驳回的 AI 题可发起「AI 重写」——把「原题 + 驳回原因 review_note + 本次修订要求 feedback + 检索条款」回喂 LLM，产出修订版（source=ai、status=PENDING、rewrite_of=原题 id、独立成新批次）重新走上述审核流程；原题保持 REJECTED 留痕。接口 `POST /api/v1/ai/questions/{qid}/rewrite`，状态机与字段见 DATABASE.md §6.1 重写流转。

## 6.2 出题 Prompt 设计

```text
你是一名安全培训专家。
根据以下企业安全知识生成考试题目：

【知识】
{knowledge}

要求：
- 生成 {count} 道 {type}（难度：{difficulty}）
- 每道题包含：题目、选项（4 个）、正确答案、答案解析
- 知识点：{knowledge_point}
- 只能输出 JSON，不要输出其他内容
```

## 6.3 输出 JSON 结构

```json
{
  "title": "高处作业安全考试",
  "questions": [
    {
      "type": "single",
      "question": "高处作业必须佩戴什么？",
      "options": ["A 安全帽", "B 安全带", "C 手套", "D 口罩"],
      "answer": "B",
      "analysis": "高处作业人员必须系安全带，防止坠落。",
      "knowledge_point": "高处作业",
      "difficulty": "medium",
      "source_law_title": "中华人民共和国安全生产法",
      "source_article_no": "第五十四条",
      "sources": [
        {"role": "answer", "law_title": "中华人民共和国安全生产法", "article_no": "第五十四条"},
        {"role": "distractor", "law_title": "建设工程安全生产管理条例", "article_no": "第二十六条"},
        {"role": "analysis", "law_title": "中华人民共和国安全生产法", "article_no": "第五十四条"}
      ]
    }
  ]
}
```

后端使用 Pydantic 定义 Schema 校验，解析失败自动重试（最多 2 次），仍失败则提示管理员重试。`sources` 逐项对应题干/选项/解析的法规依据（role: answer/distractor/analysis），干扰项确无直接条文依据时该 role 可缺省；入库前校验 `source_law_title`、`source_article_no` 与 `sources` 一致（对应 DATABASE.md question 表）。

## 6.4 组卷

- 手动组卷：管理员从题库选题（仅 status=APPROVED 的题目），分值全部指定或全部均分（混合填报 400）。
- AI 智能组卷：按「题型 × 难度 × 数量」规则（`rules: [{type, difficulty?, count}]`）+ 可选知识点过滤，从题库随机抽题（MySQL `ORDER BY RAND()`），题目数不足时返回 `warnings` 提示，全部抽不到则 400。
- 试卷配置：名称、时长（PRD 验收 30/60/90 分钟，Literal 校验）、总分、合格线（默认 60 分）。
- 组卷方式留痕 `gen_mode`（manual/ai），AI 组卷的抽题规则写入 `difficulty_ratio`（JSON）审计；分值按 `total_score` 均分，余数分摊到前若干题。
- 试卷状态 `status`：DRAFT 草稿（默认）/ PUBLISHED 已发布 / DISABLED 已停用；已发布试卷不可删除（E04 前置）。
- 接口：`POST /api/v1/papers/manual`、`POST /api/v1/papers/auto`、`GET /api/v1/papers`、`GET /api/v1/papers/{pid}`、`PUT /api/v1/papers/{pid}`、`DELETE /api/v1/papers/{pid}`，仅 SAFETY/ADMIN 可访问。

---

# 7. 隐患图片识别方案（V2 预留，本期不实现）

## 7.1 识别流程

```text
上传图片
  ↓
千问视觉大模型（qwen-vl）理解图片
  ↓
输出风险标签 + 置信度
  ↓
模型同时生成分析报告（风险等级、问题、整改建议）
  ↓
保存到 hazard.risk_report（JSON）
```

## 7.2 识别实现（千问视觉大模型）

- 调用阿里云百炼视觉接口（qwen-vl-plus / qwen-vl-max），多模态理解现场图片。
- 识别类别（V2 建议）：未佩戴安全帽、未系安全带、临边防护缺失、危险区域闯入等。
- 输出：`[{tag, confidence}]` + 自然语言分析报告。

## 7.3 风险分析报告

- 千问视觉模型结合图片理解生成”风险等级 / 问题描述 / 整改建议”。
- 优势：泛化理解能力强，可覆盖未训练的隐患类型。

## 7.4 部署

- 千问视觉模型走云端 API（百炼），**无需本地 GPU**；若数据合规要求私有化，再部署 qwen-vl 开源版。
- **本期不实现**：PRD v1.0.1 范围仅 H01 图片上传（B03 校验），识别属 V2 扩展；V2 时随 ai_service 或独立 vision_service 提供接口。

---

# 8. AI 效果评估

| 指标 | 计算方式 | 建议目标（V1.0） |
| --- | --- | --- |
| 检索召回率 Recall | 正确召回文档数 / 相关文档总数 | ≥ 80% |
| 命中率 | 检索结果中包含正确答案的比例 | ≥ 90% |
| 回答准确率 | 正确回答数 / 测试问题总数 | ≥ 85% |
| 幻觉率 | 编造/无依据回答数 / 回答总数 | ≤ 5% |
| 出题合格率 | 通过审核题目数 / 生成题目数 | ≥ 90% |
| 图片识别准确率（V2） | 正确识别数 / 识别总数 | ≥ 85% |

## 8.1 评估方法

- 构建 100+ 条安全问答测试集，人工标注标准答案。
- 每轮迭代后回归测试，比较 AI 答案与标准答案。
- 幻觉专项：知识库中不存在的问题，AI 必须回答“暂无资料”而非编造。
- 出题质量人工抽检：相关性、完整性、难度、重复率。

---

# 9. 性能与成本控制

| 项 | 目标/措施 |
| --- | --- |
| 首 token 响应 | < 3s |
| 并发 | 支持 100~200 用户并发 |
| 热点缓存 | Redis 缓存高频问题（key：cache:hot_qa:{hash}） |
| 上下文控制 | 多轮仅取最近 N 轮，控制 token 成本 |
| 模型分级 | 简单问题走轻量模型，复杂问题走强模型（可选） |
| 限流 | AI 接口按用户限流，防止滥用 |
| 异步化 | 出题、文档解析等耗时任务走队列，避免阻塞 |

---

# 10. 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 幻觉（编造答案） | 误导员工，安全风险 | 强制 RAG 引用、无资料明确拒绝、幻觉测试 |
| 知识库过期 | 回答与现行规定不符 | 文档版本管理、定期更新、标注更新时间 |
| 企业数据泄露 | 敏感规范外泄 | 知识库权限控制、日志审计、脱敏 |
| 模型服务不可用 | 功能中断 | 缓存兜底、友好降级提示、多模型切换 |
| 检索质量差 | 答非所问 | 混合检索 + Reranker + 持续评测优化切片 |

---

# 11. 配置与依赖清单

## 11.1 环境变量

```text
LLM_API_KEY=xxx
LLM_BASE_URL=https://api.xxx.com/v1
CHAT_MODEL=qwen-plus
EMBEDDING_MODEL=bge-large-zh
RERANK_MODEL=bge-reranker-v2-m3
VISION_MODEL=qwen-vl-plus
VECTOR_DB=chroma          # 生产: milvus
VECTOR_DB_URL=...
MYSQL_URL=mysql+pymysql://user:pass@host:3306/shudao
REDIS_URL=redis://host:6379/0
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE_MB=20
```

## 11.2 核心依赖

```text
langchain
langchain-openai
chromadb            # 开发环境向量库
pymilvus            # 生产环境向量库
sentence-transformers / FlagEmbedding
bge-reranker
PyMuPDF / python-docx / python-pptx
fastapi / uvicorn
sqlalchemy / pymysql / redis
# ultralytics       # V2 图片识别：千问 qwen-vl 走 API，无需本地 YOLO
pydantic
```

---

> 本方案依据 PRD 第 9 章展开，落地到 ai_service 的模块设计与模型选型，是 RAG 问答、AI 出题（及 V2 图片识别预留）开发的直接依据。
