# 第六阶段学习说明：SSE 与人工支持控制台

## 30 秒讲法

“SupportPilot 的前端不是聊天壳。客户发起请求后，后端直接遍历 LangGraph 的 `stream(values)`，把新增 TraceEvent 作为 SSE 发送；事务提交成功后才发送唯一结果。低置信度或用户要求升级时先展示工单草稿，确认才做幂等写入。支持人员用同一个 JWT/RBAC 后端完成认领、状态迁移和反馈回流。”

## 3 分钟请求链路

1. React 登录后调用 `/auth/me` 获取角色，按 `support_agent` 或租户用户切换工作台，不由前端角色判断代替后端授权。
2. 客户工作台用 Fetch POST `/agent/resolve/stream`，因为请求包含完整 JSON，而浏览器原生 EventSource 只能 GET。
3. `AgentService.resolve_events` 仍执行同一套会话锁、确认前置条件和 LangGraph；每次 state 中 Trace 长度增长，就发送尚未出现的节点事件。
4. AgentResponse、Conversation、Run 和 AuditEvent 成功持久化并 commit 后，后端才发 `result`，避免界面声称成功但数据库未落盘。
5. 前端按空行切 SSE block，并保留跨网络 chunk 的残片，不能假设一次 `reader.read()` 就得到完整 JSON。
6. 工单控制台把服务端 `version` 连同迁移提交，幂等键解决重试，version 解决不同操作并发覆盖。
7. 反馈绑定 Ticket 对应的 AgentRun，形成“回答/升级 → 人工处理 → 质量反馈”的可评测闭环。

## 技术取舍

- 选择 SSE：请求方向是单向进度，协议和运维成本低于 WebSocket；代价是断线续传和取消控制仍需补强。
- 保留 JSON REST 工单 API：工单状态操作是短事务，不需要流式协议。
- 不引入 Redux：当前跨页面共享状态只有认证，组件状态足够；规模扩大再引入状态库。
- 不把 RBAC 放到路由隐藏逻辑：前端只改善体验，所有权限仍由后端数据库用户与租户规则强制执行。

## 高频追问

- 为什么最后结果必须 commit 后再发？——否则客户端可能收到成功，但随后事务失败，形成不可解释的不一致。
- TCP chunk 和 SSE event 有什么区别？——chunk 是传输分片，可能切断任意字符；event 由空行界定，解析器必须缓存不完整 block。
- SSE 为什么不直接用 EventSource？——这个请求需要 POST JSON 和 Authorization Header，原生 EventSource 不适合，所以使用 Fetch Stream。
- 幂等键和 optimistic locking 为什么前端都要带？——前者保证相同请求重试一次副作用，后者防止不同请求基于旧版本互相覆盖。
- 页面隐藏按钮能阻止越权吗？——不能；按钮只做 UX，真正授权在 FastAPI 依赖和 service 层。
