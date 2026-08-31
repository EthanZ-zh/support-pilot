# 第四阶段学习说明：受控 Agent 首个增量

## 架构变化

Agent 层位于 API 与既有 RAG/业务服务之间。`DecisionProvider` 只负责结构化意图判断，LangGraph 负责节点与分支，确定性代码负责安全和业务真值，PostgreSQL 保存运行快照与 Trace。CI 使用确定性 Provider，真实适配器使用百炼 Qwen3.7 Plus。

## 一次请求怎么走

1. API 校验用户与 `AgentRequest`。
2. `preflight_safety` 在外部调用前拦截基础 Prompt Injection 和已知高风险动作，并对密钥模式脱敏。
3. `DecisionProvider` 最多尝试两次。Qwen 请求使用严格 JSON Schema 和 15 秒超时；失败时输出 `unknown`，不无限重试。
4. `risk_gate` 根据结构化意图分级，但不能覆盖安全预检的拒绝结果。
5. 只读业务工具要求显式业务参数；缺参进入 `needs_clarification` 并把 pending intent/context 保存到 `agent_conversations`。
6. RAG 只有在 Answerability Gate 通过时返回抽取式答案和引用。
7. 下一轮复用 `session_id` 时从领域表恢复；补参和确认轮次跳过模型分类。
8. 工单先生成草稿；确认请求必须有客户端幂等键，内部使用稳定会话键调用原有 `SupportService`。
9. 每个节点写 Trace，最终响应、状态、Token 和估算成本保存到 `agent_runs` 并记审计。

## 技术取舍

- 先用 DAG 而不是自由 ReAct 循环，便于证明终止性和副作用边界。
- Qwen 当前只做意图分类；回答继续使用可追溯的抽取式结果，待生成评测口径建立后再让模型生成。
- 业务代码不导入厂商 SDK；OpenAI 兼容 HTTP 细节封装在 Qwen Provider 内，换 Provider 不改工作流。
- 只把脱敏消息和“已提供哪些上下文字段”发给模型，不发送租户 ID；API Key 只进入 Authorization Header，Base URL 限制为百炼北京域名。
- `AgentConversation` 保存可查询的业务恢复状态，`AgentRun` 保存每轮证据；LangGraph checkpointer 留给未来的节点级 interrupt 恢复。
- 客户端幂等键只保存哈希，内部稳定会话键兜住“工单已提交、会话尚未更新”这一崩溃窗口。
- Provider 故障转换为可解释升级，不把 SDK 异常或内部提示词返回给用户。

## 你要能讲清的内容

### 30 秒

“我用 LangGraph 把技术支持请求做成显式 DAG，Qwen3.7 Plus 通过 Provider 和严格 JSON Schema 只输出首轮意图。缺参和工单草稿进入领域会话表，下一轮按 session_id 恢复且不重复调用模型。工单确认同时使用客户端 Key 哈希和稳定会话幂等键，并发确认也只创建一张工单。”

### 3 分钟

沿 `API → load conversation → preflight_safety → classify/resume → risk_gate → tool/draft/confirm → AgentConversation + AgentRun + AuditEvent` 讲完整请求链路，再说明为什么恢复轮次不调用模型、为什么客户端 Key 之外还需要稳定内部 Key。

### 深入追问

- 如果模型把退款误判为知识查询，为什么仍不会执行退款？
- Provider 结构化输出通过 Schema 后，为什么仍要做业务参数校验？
- DAG 和 ReAct 循环分别适合什么场景？
- 状态快照与可恢复 checkpoint 有什么区别？
- 如何测工具参数准确率和高风险误执行率？
