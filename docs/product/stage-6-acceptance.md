# 第六阶段全栈体验验收

状态：自动化验收通过，真实浏览器人工走查待记录

## 1. 业务目标与请求链路

客户和支持人员不再依赖 Swagger 完成演示。客户登录后提交问题，浏览器消费真实 LangGraph 节点事件；最终结果同时展示风险、引用、模型用量和工单确认。升级人工后，支持人员可在同一控制台认领、推进状态并提交反馈。

```text
React login → local JWT → POST /agent/resolve/stream
  → LangGraph stream(values) → progress SSE × N
  → transaction commit → result SSE
  → answer / citations / trace / ticket confirmation
  → ticket queue → claim → transition → feedback
```

## 2. 已实现验收项

- [x] React + TypeScript + Vite 单页控制台，可响应桌面和移动宽度；
- [x] 登录、Token 恢复和退出流程接入真实 JWT API；
- [x] 客户可提交自然语言问题及可选结构化上下文；
- [x] 后端通过 `text/event-stream` 逐节点发送真实 TraceEvent，而非前端定时器伪造进度；
- [x] 流式结果展示 outcome、intent、风险级别、回答、引用 URI、Trace ID 和模型用量；
- [x] TicketDraft 必须由客户显式确认才创建工单，确认请求携带独立幂等键；
- [x] `support_agent` 可查看队列、认领、按确定性状态机迁移工单；
- [x] 工单版本冲突时刷新服务端状态，不盲目覆盖；
- [x] 人工反馈关联 AgentRun，支持采纳、编辑、拒绝和知识缺口标记；
- [x] SSE 错误以受控 `error` 事件返回，意外异常不向浏览器暴露堆栈；
- [x] 前端没有远程字体、分析脚本或第三方运行时依赖。

## 3. 自动化证据

- `npm run lint`：通过；
- `npm run test`：2 个测试文件、4 个测试通过，覆盖跨 chunk SSE 解析、受控错误、客户实时轨迹和人工认领；
- `npm run build`：TypeScript 与 Vite 生产构建通过，JS gzip 约 64.70 kB；
- `pytest tests/integration/test_agent_api.py -q`：14 个集成测试通过，含真实 PostgreSQL 下 progress 顺序和流内前置条件错误；
- `ruff` 与 `mypy`：新增后端流式实现通过。

## 4. 明确限制

- JWT 暂存在 `localStorage`，适合本地作品演示；生产 Web 应优先改用受 CSRF 防护的 HttpOnly Cookie 或 BFF；
- SSE 使用 POST + Fetch Stream，因此自实现了事件解析；不依赖只支持 GET 的原生 EventSource；
- 用户关闭连接时数据库会回滚未提交运行，但当前没有显式的前端 AbortController；
- 工单列表是最多 100 条的 MVP 队列，没有服务端游标分页、搜索或实时推送；
- 已用 jsdom 验证关键交互，但尚未记录 Chrome/Edge 的人工端到端走查证据。
