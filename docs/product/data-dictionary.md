# SupportPilot 领域数据字典

本字典描述产品层语义，不等同于最终 SQLAlchemy 模型或数据库迁移。实现阶段允许调整存储细节，但不得悄悄改变字段含义、租户边界或风险规则。

## 1. 通用约定

- 主键统一使用不可预测的 UUID；对外展示编号与内部主键分离。
- 租户数据实体必须带 `tenant_id`，查询默认强制租户过滤。
- 时间使用带时区的 UTC 时间戳，界面按用户时区展示。
- 所有枚举在 API Schema 和数据库约束中显式定义，不使用自由文本承载状态。
- 写入实体包含 `created_at`、`updated_at`；需要审计的实体还包含操作者和版本号。
- 文本进入日志、检索索引或模型前执行 Secret/敏感标识检测与脱敏。
- `data_origin` 至少区分 `synthetic`、`human_labeled`、`public`；演示业务数据固定为 `synthetic`。

## 2. 身份与租户

### Tenant（租户）

| 字段 | 类型/枚举 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 内部租户标识 |
| display_name | string | 是 | 明确为虚构的展示名称 |
| plan_id | UUID | 是 | 当前套餐 |
| region | enum | 是 | 主要服务区域，如 `ap-southeast-1` |
| status | `active/suspended/closed` | 是 | 由确定性规则使用 |
| data_origin | enum | 是 | MVP 固定 `synthetic` |

### User（用户）

| 字段 | 类型/枚举 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 用户标识 |
| tenant_id | UUID/null | 条件 | 客户用户必须有；内部支持人员可为空 |
| email | string | 是 | 唯一合成登录标识，规范化为小写 |
| password_hash | string | 是 | Argon2id 哈希，永不返回 API |
| display_name | string | 是 | 合成展示名，不使用真实个人数据 |
| role | `customer_developer/tenant_admin/support_agent/knowledge_admin` | 是 | RBAC 基础角色 |
| status | `active/disabled` | 是 | 禁用用户不能调用租户工具 |

### SessionContext（会话上下文）

| 字段 | 类型/枚举 | 必填 | 说明 |
|---|---|---:|---|
| session_id | UUID | 是 | 一次支持会话 |
| user_id | UUID/null | 条件 | 未认证咨询可为空 |
| tenant_id | UUID/null | 条件 | 公开知识问题可为空；租户查询必须有 |
| auth_level | `anonymous/authenticated/verified` | 是 | 决定工具可见性，不由模型修改 |
| locale | string | 是 | MVP 默认 `zh-CN` |

## 3. 套餐、权限与额度

### Plan（套餐）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 套餐标识 |
| code | string | 是 | 稳定代码，如 `starter/pro/enterprise` |
| name | string | 是 | 展示名 |
| effective_from/to | datetime/null | 是 | 规则生效区间 |

### Entitlement（功能权益）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| tenant_id | UUID | 是 | 租户边界 |
| feature_code | string | 是 | 功能稳定代码 |
| enabled | boolean | 是 | 确定性授权结果 |
| source | `plan/override/trial` | 是 | 权益来源 |
| effective_from/to | datetime/null | 是 | 有效区间 |

唯一语义：同一租户、功能和有效区间不得产生不可消解的并行有效记录。

### QuotaSnapshot（额度快照）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| tenant_id | UUID | 是 | 租户边界 |
| metric_code | string | 是 | 如 `api_requests_monthly` |
| limit | integer | 是 | 非负额度上限 |
| used | integer | 是 | 非负已用量 |
| period_start/end | datetime | 是 | 统计周期 |
| measured_at | datetime | 是 | 数据新鲜度依据 |

模型不得自行计算授权结论；工具应返回剩余额度、是否超限和快照时间。

## 4. 知识与检索

### KnowledgeDocument（知识文档）

| 字段 | 类型/枚举 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 文档标识 |
| title | string | 是 | 标题 |
| doc_type | `guide/api_reference/faq/known_issue/runbook/release_note/ticket_resolution` | 是 | 来源类别 |
| product_version | string/null | 条件 | 与版本相关时必填 |
| applicable_plans | string[] | 是 | 空数组表示所有套餐 |
| effective_from/to | datetime/null | 是 | 时效范围 |
| authority | `official/synthetic_ticket/public_reference` | 是 | 冲突处理依据 |
| data_origin | enum | 是 | 数据来源类别 |
| source_uri | string | 是 | 项目内路径或公开 URL |
| license | string/null | 条件 | 公开资料必填 |
| checksum | string | 是 | 去重与变更检测 |
| status | `draft/published/superseded/archived` | 是 | 仅 `published` 默认参与检索 |

### KnowledgeChunk（知识片段）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 可引用片段标识 |
| document_id | UUID | 是 | 所属文档 |
| ordinal | integer | 是 | 文档内顺序 |
| content | text | 是 | 脱敏后的片段内容 |
| heading_path | string[] | 是 | 引用上下文 |
| token_count | integer | 是 | 摄取统计 |
| metadata | object | 是 | 版本、套餐、区域等过滤字段 |

### RetrievalEvidence（检索证据）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| chunk_id | UUID | 是 | 证据片段 |
| retrieval_rank | integer | 是 | 最终排序位置 |
| keyword_rank/vector_rank | integer/null | 否 | 双路召回位置 |
| fused_score/rerank_score | number/null | 否 | 分数只用于排序与分析，不直接等于答案置信度 |
| filters_applied | object | 是 | 版本、套餐、时间等过滤条件 |
| citation_label | string | 是 | 回答中的稳定引用标签 |

## 5. 服务状态与事故

### ServiceComponent（服务组件）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 组件标识 |
| code | string | 是 | 如 `rest_api/webhook_delivery` |
| region | string | 是 | 服务区域 |
| status | `operational/degraded/partial_outage/major_outage/maintenance` | 是 | 当前状态 |
| observed_at | datetime | 是 | 状态新鲜度 |

### Incident（事故）

| 字段 | 类型/枚举 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 内部标识 |
| public_code | string | 是 | 可展示事故编号 |
| title | string | 是 | 事故标题 |
| severity | `sev1/sev2/sev3/sev4` | 是 | 确定性枚举 |
| status | `investigating/identified/monitoring/resolved` | 是 | 状态机 |
| component_ids | UUID[] | 是 | 受影响组件 |
| regions | string[] | 是 | 受影响区域 |
| started_at/resolved_at | datetime/null | 是 | 事故窗口 |
| customer_message | text | 是 | 可对客户披露的合成说明 |
| internal_notes | text/null | 否 | 客户不可见，必须按角色过滤 |

## 6. 会话、Agent 与工具

### SupportRequest（支持请求）

| 字段 | 类型/枚举 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 单次请求标识 |
| session_id | UUID | 是 | 所属会话 |
| raw_message | text | 是 | 原始输入，持久化前脱敏 |
| intent | `knowledge/entitlement/quota/incident/diagnosis/ticket_request/high_risk/unknown` | 是 | 结构化路由结果 |
| risk_level | `R0/R1/R2/R3` | 是 | 规则与模型共同识别，规则可上调风险 |
| status | `received/running/answered/escalated/failed/refused` | 是 | 请求处理状态 |
| trace_id | string | 是 | 关联可观察链路 |

### AgentRun（Agent 运行）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 一次有限工作流运行 |
| request_id | UUID | 是 | 对应支持请求 |
| workflow_version | string | 是 | 可复现版本 |
| provider/model | string | 是 | 评测与成本记录 |
| started_at/finished_at | datetime/null | 是 | 延迟计算 |
| outcome | enum | 是 | `answered/escalated/refused/cancelled/failed` |
| token_usage/estimated_cost | object/null | 否 | Provider 可用时记录，不伪造缺失值 |

### AgentConversation（可恢复会话状态，已实现）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| session_id | UUID | 是 | 客户端跨轮复用的主键 |
| user_id/tenant_id | UUID/UUID-null | 是/条件 | 会话所有权与租户边界，创建后不可切换 |
| status | enum | 是 | `active/awaiting_clarification/awaiting_confirmation/completed/cancelled` |
| pending_intent | enum/null | 否 | 缺参或待确认时恢复原路由，不重新调用模型 |
| pending_context | object | 是 | 已校验、已脱敏的跨轮业务参数 |
| ticket_draft/ticket_result | object/null | 否 | 待确认草稿与已创建工单结果 |
| confirmation_key_hash | string/null | 否 | 客户端幂等键的 SHA-256，不保存原文 |
| version | integer | 是 | 会话状态演进版本，最小为 1 |

### ToolInvocation（工具调用）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 调用标识 |
| agent_run_id | UUID | 是 | 所属运行 |
| tool_name | string | 是 | 注册工具名 |
| risk_level | enum | 是 | 工具静态风险级别 |
| input_redacted/output_redacted | object | 是 | Schema 校验且已脱敏 |
| status | `started/succeeded/failed/timed_out/denied` | 是 | 调用结果 |
| duration_ms | integer/null | 否 | 性能证据 |
| error_code | string/null | 否 | 稳定错误分类，不记录完整 Secret |

### AnswerDecision（回答门控）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| agent_run_id | UUID | 是 | 所属运行 |
| answerable | boolean | 是 | 是否允许自动答复 |
| evidence_coverage | number | 是 | `[0,1]`，口径由评测实现固定 |
| has_conflict | boolean | 是 | 是否存在未消解冲突 |
| required_context_missing | string[] | 是 | 缺失参数列表 |
| decision_reasons | enum[] | 是 | 如 `sufficient_evidence/tool_failure/high_risk` |
| response_mode | `auto_reply/clarify/escalate/refuse` | 是 | 最终处置 |

## 7. 工单与人工处理

### Ticket（工单）

| 字段 | 类型/枚举 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 内部标识 |
| public_code | string | 是 | 可展示编号 |
| tenant_id | UUID | 是 | 租户边界 |
| source_request_id | UUID | 是 | 来源请求 |
| idempotency_key | string | 是 | 创建副作用去重；与作用域组成唯一约束 |
| status | `open/triaged/in_progress/waiting_customer/resolved/closed` | 是 | 有限状态机 |
| severity | `low/medium/high/urgent` | 是 | 规则计算并允许授权人员调整 |
| category | enum | 是 | 与 intent 对齐的稳定分类 |
| summary/description | text | 是 | 脱敏问题摘要和详情 |
| diagnostic_context | object | 是 | 错误码、区域、时间、脱敏 request_id 等 |
| escalation_reason | enum | 是 | `user_requested/low_answerability/high_risk/tool_failure/security_or_privacy/unknown` |
| assignee_id | UUID/null | 否 | 支持人员 |
| version | integer | 是 | 乐观并发控制 |

### TicketTransition（工单状态变化，已实现）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| ticket_id | UUID | 是 | 工单 |
| from_status/to_status | enum | 是 | 状态转换 |
| actor_id | UUID | 是 | 操作者 |
| reason | string | 是 | 变更理由 |
| created_at | datetime | 是 | 发生时间 |

### HumanFeedback（人工反馈，已实现）

| 字段 | 类型/枚举 | 必填 | 说明 |
|---|---|---:|---|
| ticket_id/agent_run_id | UUID | 是 | 关联工单与运行 |
| reviewer_id | UUID | 是 | 反馈人 |
| disposition | `accepted/edited/rejected` | 是 | 对建议的处理 |
| resolution_category | enum | 是 | 最终解决分类 |
| knowledge_gap | boolean | 是 | 是否存在知识缺口 |
| comment | text/null | 否 | 脱敏说明 |

反馈仅进入候选数据集，不自动成为权威知识。

## 8. 审计、幂等与评测

### AuditEvent（审计事件）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | UUID | 是 | 事件标识 |
| tenant_id | UUID/null | 条件 | 涉及租户时必填 |
| actor_type/actor_id | enum/string | 是 | `user/agent/system` 及标识 |
| action | string | 是 | 稳定动作代码 |
| resource_type/resource_id | string | 是 | 被操作对象 |
| outcome | `success/failure/denied` | 是 | 结果 |
| reason_code | string | 是 | 可聚合原因 |
| metadata_redacted | object | 是 | 脱敏元数据 |
| trace_id | string | 是 | 与请求链路关联 |
| created_at | datetime | 是 | 不可变事件时间 |

### IdempotencyRecord（幂等记录）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| scope | string | 是 | 如 `tenant:create_ticket` |
| key | string | 是 | 客户端键或稳定派生键 |
| request_hash | string | 是 | 检测同键不同载荷 |
| resource_id | UUID/null | 否 | 成功创建的资源 |
| status | `processing/succeeded/failed` | 是 | 并发与重试协调 |
| expires_at | datetime | 是 | 保留期限 |

### EvaluationCase（评测样本）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | string | 是 | 稳定样本编号 |
| dataset_version | string | 是 | 数据集版本 |
| data_origin | enum | 是 | 合成、人工标注或公开 |
| scenario | enum | 是 | 正常、缺参、无答案、失败、重复、并发、越权、注入等 |
| input | object | 是 | 脱敏测试输入 |
| expected | object | 是 | 意图、工具、证据、处置和副作用期望 |
| labels | string[] | 是 | 切片分析标签 |

## 9. 核心关系与不变量

- 一个 `Tenant` 有一个当前 `Plan`，可有多个按时间生效的 `Entitlement` 和 `QuotaSnapshot`。
- 一个 `SupportRequest` 对应一个或多次可重试的 `AgentRun`，但一次业务写入由幂等记录保证至多产生一个目标资源。
- 一个 `AgentConversation` 属于一个用户和至多一个租户；确认工单时用稳定会话键保证该会话至多创建一个 Ticket。
- `RetrievalEvidence` 必须引用已发布且满足元数据过滤的 `KnowledgeChunk`。
- `Ticket.tenant_id` 必须与来源请求的有效租户上下文一致。
- 客户用户不能读取 `Incident.internal_notes`、其他租户数据、内部 trace 原文或未脱敏工具输出。
- 工单状态只能按显式状态机转换；`closed` 不允许被 Agent 自动设置。
- R3 工具不进入 MVP 的可执行工具注册表；出现相应意图只能拒绝或升级。
