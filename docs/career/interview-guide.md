# SupportPilot 面试讲解与追问

## 30 秒项目介绍

“SupportPilot 是我为虚构 B2B SaaS 做的技术支持 Agent。它不只聊天：先识别意图和风险，再检索带引用的知识或调用确定性只读工具；低置信度会升级，创建工单必须用户确认，支持人员再通过状态机处理并回传反馈。系统用 LangGraph 编排、PostgreSQL/pgvector 做混合检索，后端 FastAPI，前端 React/SSE，并用 JWT/RBAC、幂等、乐观锁和审计控制副作用。”

## 3 分钟技术讲解

从 `/agent/resolve/stream` 开始：JWT 解析后会回查数据库用户，确认角色与租户没有漂移；AgentService 锁定会话并合并上轮缺失上下文。LangGraph 先做 Prompt Injection/高风险预检，再通过可替换 DecisionProvider 分类。R1 请求走 RAG 或确定性业务工具；R3 在模型和工具前拒绝。

RAG 在 SQL 层做 published/version/plan 过滤，再走 PostgreSQL 关键词和 pgvector 向量召回，RRF 融合后用 Provider Rerank。Answerability Gate 决定回答还是升级，引用保留 document/chunk/source URI。浏览器收到的进度直接来自 LangGraph state，不是假的 loading；数据库提交 AgentRun、Conversation 和 AuditEvent 后才返回最终结果。

写操作先生成 TicketDraft。用户确认时要求 Idempotency-Key，数据库唯一约束防重复；人工认领和状态迁移还带 expected_version，防止两个不同操作覆盖。RBAC 和租户过滤在服务端强制，前端隐藏按钮不作为安全边界。最后 HumanFeedback 绑定原 Ticket 和 AgentRun，支持离线复盘但不自动改知识库。

## 深入追问

### 为什么采用模块化单体？

当前团队、流量和事务范围都小，Agent、工单、审计共享强一致数据库。单体更容易完成纵向闭环和调试；模块边界与 Provider 接口已保留，只有独立伸缩或组织边界出现后才拆服务。

### RRF 解决什么问题？

关键词分数和向量相似度量纲不同，直接加权难校准。RRF 只使用排名，以 `1/(k+rank)` 融合，能奖励双路都找到的证据；代价是忽略原始分差，所以融合后仍需 Reranker 和 Gate。

### Answerability 为什么不能只看 top-1 分数？

分数高不代表覆盖全部主张，也可能是过期或冲突证据。当前 Gate 已看阈值和冲突，但 401/403 失败说明还缺多证据覆盖；下一步应对问题拆主张、选择多 chunk 并逐主张绑定引用。

### 如何避免 LLM 乱调工具？

LLM 只输出严格 Schema 的意图与参数候选，所有外部输入由 Pydantic 校验；权限、租户、状态机和业务数字由代码/数据库决定；高风险工具根本不在自动执行集合中，并限制重试和 LangGraph recursion limit。

### 幂等与数据库事务如何配合？

请求先在作用域内写 processing idempotency record，Key + scope 唯一；同 Key 同 payload 成功后重放结果，不同 payload 冲突。Ticket 行锁、version 和状态变更与幂等完成记录在同一事务，避免“副作用成功但幂等仍失败”。

### 怎么评价模型而不是只看最终回答？

分层评测检索 Recall/MRR/nDCG、Answerability、意图 F1、安全升级 Recall、工具参数/成功率、工单完整率、副作用、延迟/Token/成本。确定性 Provider 做可重复回归，真实 Qwen 结果单独报告，不能混用口径。

### 当前最值得改的三个点？

1. 将 RAG calibration/test 分离，加入真实公开文档、难负例和逐主张引用评测；
2. 增加真实浏览器 E2E、SSE 取消/断线恢复和队列分页；
3. 用 OIDC + HttpOnly Cookie 替换本地 JWT/localStorage，并把 OTel 接入 Collector、指标与日志关联。
