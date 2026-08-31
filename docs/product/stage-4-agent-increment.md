# 第四阶段 Agent：首个可运行增量

## 1. 本增量业务目标

把第三阶段的知识检索和第二阶段的确定性业务工具接入一个受控工作流，让自然语言请求能够经过意图识别、风险门控、工具执行和失败降级。当前增量用于验证编排边界，不代表第四阶段全部完成。

## 2. 请求链路

```text
POST /api/v1/agent/resolve
  → CurrentUser 身份边界（首增量曾用 X-User-Id，现已由 JWT 提供）
  → 确定性安全预检与密钥脱敏
  → DecisionProvider 意图分类（最多 2 次尝试）
  → 确定性风险门控
  ├─ knowledge → 混合检索 → Answerability Gate → 抽取式回答 + 引用
  ├─ entitlement/quota/incident → 参数完整性 → 确定性只读工具
  ├─ ticket_request → 仅生成草稿 → 等待用户确认
  ├─ high_risk → 拒绝，不调用执行工具
  └─ unknown/tool failure → 有原因的人工升级
  → 持久化 AgentRun 状态快照、节点 Trace 和审计记录
  → AgentConversation 保存待补参数/草稿，下一轮按 session_id 恢复
```

工作流当前是 DAG，没有自主循环；LangGraph `recursion_limit=12` 是第二道上限。Qwen Provider 也不得绕过风险门控、租户授权、Answerability Gate 或工单幂等逻辑。

## 3. 当前完成标准

- [x] Agent 输入、Provider 决策、响应和 Trace 使用严格 Schema；
- [x] 决策 Provider 与厂商 SDK 隔离，确定性 Provider 可用于 CI；
- [x] Qwen3.7 Plus 适配器使用严格 JSON Schema、HTTPS、15 秒超时和有限重试；
- [x] Prompt Injection 与已知高风险动作在调用外部模型前拦截，消息中的密钥模式先脱敏；
- [x] Qwen Base URL 只允许北京区百炼共享或业务空间专属域名；
- [x] 记录模型调用数、Token 与带价格快照的估算成本；
- [x] 知识问题只能在 Gate 可回答时返回，并携带真实检索引用；
- [x] 业务工具缺参时请求补充，不让 Provider 猜业务主键；
- [x] 高风险请求和基础 Prompt Injection 模式在工具前被拦截；
- [x] 工单请求只生成草稿，没有确认不产生副作用；
- [x] 缺参状态跨请求恢复，恢复轮次不重复调用模型；
- [x] 工单确认必须带 `Idempotency-Key`，相同 Key 重放、换 Key 409；
- [x] 会话级稳定内部幂等键保证并发确认只创建一张工单；
- [x] 取消、跨用户会话拒绝和安全拒绝后保留草稿均有集成测试；
- [x] Provider 失败只有有限重试，并降级到人工处理；
- [x] 运行结果和节点 Trace 持久化到 PostgreSQL；
- [x] 集成测试覆盖知识回答、缺参、高风险、工单草稿和 Prompt Injection。

## 4. 明确未完成

- Qwen3.7 Plus 已完成 7 条真实 Provider 冒烟验证；样本过小，不能表述为生产准确率；
- 模型当前只做意图分类，知识答案仍是有引用的抽取式结果；
- 已实现领域级多轮恢复；尚未实现从任意 LangGraph 节点中间恢复的 checkpointer；
- 后续已完成 80 条确定性 Agent 场景评测；真实 Qwen 仍只有 7 条冒烟，二者指标不可混用；
- Prompt Injection 当前只有基础规则，完整分层防护属于第五阶段；
- JWT/RBAC 与人工接管 API 已在第五阶段完成；人工工作台和 SSE 属于第六阶段。

因此本文件只记录“第四阶段首个纵向增量”；阶段最终边界和评测结果见 `stage-4-acceptance.md`。
