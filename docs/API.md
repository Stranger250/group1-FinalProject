# 蜀道安全助手 接口文档（API.md）

> 版本：v1.0 · 日期：2026-08-14 · 来源：由文档与代码一致性核对产出，替代缺失的接口契约文档。
> 在线文档：后端启动后访问 `/docs`（Swagger UI，FastAPI 自动生成，字段级契约以其为准）。
> 统一约定：
> - 基础路径 `/api/v1`；响应统一 `{code, message, data}`（业务成功 code=200）；
> - 鉴权：`Authorization: Bearer <access_token>`（登录接口返回）；未登录 401、越权 403；
> - 参数校验失败 422（`{code:422, message, data:null}`）；404 用于「不存在/他人资源掩码」；
> - 角色：EMPLOYEE=1 / SAFETY=2 / ADMIN=3；管理类接口 `_MANAGE`=SAFETY+ADMIN，用户管理仅 ADMIN。

---

## 1. 认证 auth（/api/v1/auth）

| 方法 | 路径 | 说明 | 鉴权 |
| --- | --- | --- | --- |
| POST | /auth/register | 注册（强制 EMPLOYEE；username 3-64、password 6-64 且 utf-8≤72 字节） | 公开 |
| POST | /auth/login | 登录（OAuth2 表单 username/password → access_token+user） | 公开 |
| GET | /auth/me | 当前用户信息 | 登录 |
| PUT | /auth/profile | 修改资料（name 必填、phone 数字、email 格式） | 登录 |
| PUT | /auth/password | 修改密码（校验原密码，新旧不同） | 登录 |
| POST | /auth/avatar | 上传头像（jpg/png/jpeg ≤5MB → 更新 user.avatar） | 登录 |

## 2. 用户管理 user（/api/v1/users，仅 ADMIN）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /users | 用户列表（keyword/role_id/status 筛选 + 分页；page≤100000、page_size≤100） |
| PUT | /users/{uid} | 更新角色/状态（禁自身/降级自身 400；至少保留一个启用管理员） |
| POST | /users/{uid}/reset-password | 重置密码（返回一次性临时密码） |

## 3. 隐患管理 hazard（/api/v1/hazards）

| 方法 | 路径 | 说明 | 鉴权 |
| --- | --- | --- | --- |
| POST | /hazards/upload | 图片上传（jpg/png/jpeg + MIME 白名单 ≤5MB → /uploads/YYYYMMDD/uuid.ext） | 登录 |
| POST | /hazards/analyze | AI 视觉识别（类型/等级/描述/bbox/标注图；未配置 503 降级） | 登录 |
| POST | /hazards | 隐患上报（description/level 必填；编号 HZ+yyyyMMdd-序号；多图≤9） | 登录 |
| GET | /hazards | 列表（status/level/type/keyword/时间区间 + sort(create_time\|level)/order + 分页） | 登录 |
| GET | /hazards/{hid} | 详情（图片 + 时间线倒序；全员可见，透明度设计） | 登录 |
| POST | /hazards/{hid}/close | 一键闭环 WAIT_PROCESS→FINISHED（重复闭环 400） | SAFETY/ADMIN |

## 4. AI 助手 chat（/api/v1/ai，任意登录用户）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /ai/chat | 智能问答（**SSE**：meta → delta* → [ping] → done；敏感词预检 400；`Cache-Control: no-cache`） |
| POST | /ai/conversations | 新建会话（title 缺省「新会话」） |
| GET | /ai/conversations | 会话列表（按更新时间倒序，分页） |
| PUT | /ai/conversations/{cid} | 重命名（title 1-64） |
| DELETE | /ai/conversations/{cid} | 删除（级联 message/message_source） |
| GET | /ai/conversations/{cid}/messages | 消息列表（assistant 内联 sources） |
| GET | /ai/source/{message_id} | 回答引用列表（非本人/非 assistant 400/404） |
| GET | /ai/article | 查看原文（doc_id+article_no → 父块全文；缺参 422） |
| GET | /ai/quick-questions | 快捷提问列表 |
| POST | /ai/feedback/{message_id} | 回答反馈（value: -1/0/1；仅 assistant 消息） |

## 5. 题库 exam（/api/v1/questions，SAFETY/ADMIN）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /questions | 列表（type/difficulty/knowledge_point/status/source/batch_id/keyword + 分页） |
| GET | /questions/{qid} | 详情 |
| POST | /questions | 手工录入（type: SINGLE/MULTIPLE/JUDGE/FILL/**SUBJECTIVE**；answer/analysis 必填；直接 APPROVED） |
| PUT | /questions/{qid} | 编辑（编辑禁改 type 由前端约束；改答案/选项重新校验） |
| DELETE | /questions/{qid} | 删除（被试卷引用 400） |

## 6. AI 出题 ai（/api/v1/ai，SAFETY/ADMIN）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /ai/generate | AI 生成（knowledge_point 或 reference_text 必填；count 5-50，>20 分轮；同 batch_id；PENDING 入草稿；LLM 失败 502） |
| POST | /ai/doc | 上传参考文档（txt/md/pdf/docx ≤5MB → 纯文本；>5000 字截断 truncated=true；非法扩展名 400、超大 413） |
| GET | /ai/batches | 批次列表（pass_rate=approved/(approved+rejected)） |
| GET | /ai/batches/{batch_id} | 批次题目详情 |
| GET | /ai/stats | 出题统计（批次/通过率/题型难度分布） |
| POST | /ai/questions/{qid}/review | 单题审核（APPROVE/REJECT；驳回必填 review_note；仅 source=ai） |
| POST | /ai/questions/{qid}/rewrite | AI 重写（仅 REJECTED 的 AI 题；就地替换回 PENDING；LLM 失败 502） |
| POST | /ai/batches/{batch_id}/review | 整批/部分批量审核（先全预检再单事务落库） |

## 7. 试卷 paper（/api/v1/papers，SAFETY/ADMIN）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /papers/manual | 手动组卷（仅 APPROVED 题；分值全指定或全均分；和=总分；同题重复 400） |
| POST | /papers/auto | AI 智能组卷（rules 按题型×难度抽题；不足返回 warnings；一条未抽到 400） |
| GET | /papers | 列表（gen_mode/status/keyword + 分页） |
| GET | /papers/{pid} | 详情（含题目预览与答案） |
| PUT | /papers/{pid} | 更新（PUBLISHED 锁总分/及格线；有进行中考试锁时长） |
| DELETE | /papers/{pid} | 删除（PUBLISHED 或有考试记录 400） |

## 8. 在线考试 exam_running（/api/v1/exams，任意登录用户）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /exams/papers | 公开选卷（仅 PUBLISHED，脱敏无题目/答案；含 ongoing_record_id） |
| GET | /exams/records | 我的考试记录（分页；含 reason/cheat_count） |
| POST | /exams/start | 开始考试（未发布 400；并发复用进行中记录；超时懒校验自动交卷） |
| GET | /exams/{record_id} | 刷新恢复（进行中=题目+已存答案；已交卷=成绩单；`Cache-Control: no-store`） |
| POST | /exams/{record_id}/save | 增量保存（重复 question_id 去重取末值；已交卷幂等返回成绩单） |
| POST | /exams/{record_id}/submit | 交卷+自动阅卷（条件 UPDATE 防并发双交；状态机 timeout>cheat_limit>manual） |
| POST | /exams/{record_id}/switch | 切屏上报（服务端 max 合并；>3 次（第 4 次）自动交卷） |
| GET | /exams/{record_id}/result | 成绩单（总分/合格/逐题作答 vs 判分快照/解析；未交卷 400） |

## 9. 其他

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | / | 健康检查 `{status:ok, module}` |
| GET | /uploads/* | 上传文件静态访问（main.py 挂载 StaticFiles） |

## 10. 判分口径（E05）

- SINGLE/JUDGE：精确匹配；MULTIPLE：集合完全一致（漏选/错选 0 分）；FILL：空数一致+逐空匹配；
- **SUBJECTIVE 解答题**：参考答案分号分隔要点，作答包含要点按 `命中要点数/总要点数 × 分值`（四舍五入）计分。

## 11. 审计日志（audit_log）

关键操作（登录/登录失败/禁用账号登录、隐患闭环、题目审核、试卷状态变更、用户更新/重置密码）写入 `audit_log` 表：
`user_id/username/action/target_type/target_id/detail/ip/create_time`；写失败仅告警不阻断业务。
