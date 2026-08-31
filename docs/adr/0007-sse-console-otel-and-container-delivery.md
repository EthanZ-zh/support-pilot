# ADR-0007：SSE 控制台、OTLP 可观测性与容器交付

- 状态：Accepted
- 日期：2026-08-31

## 背景

前五阶段已能通过 API 完成受控 Agent 和人工工单闭环，但作品演示仍依赖 Swagger，节点过程不可见，运行环境也缺少统一构建入口。第六、七阶段需要在不拆微服务的前提下补齐体验和可复现性。

## 决策

1. 使用 React + TypeScript + Vite 构建一个按角色切换的控制台；业务授权仍全部由后端执行。
2. Agent 进度使用 POST Fetch Stream + SSE。后端直接转发 LangGraph `stream_mode="values"` 产生的新增 TraceEvent，持久化提交后才发送最终结果。
3. FastAPI 和 SQLAlchemy 使用 OpenTelemetry 自动埋点，通过 OTLP/HTTP 导出；默认关闭，避免本地无 Collector 时产生噪声和失败重试。
4. 保持模块化单体，Docker Compose 只编排 API、静态前端和 PostgreSQL/pgvector；不引入消息队列、Kubernetes 或独立 Agent 服务。
5. CI 将后端、前端和容器构建拆成独立作业，以便快速定位失败域。

## 替代方案

- WebSocket：适合双向实时协作，但当前只有服务器到浏览器的节点进度，连接管理成本没有收益。
- EventSource：浏览器 API 简单，但不支持本场景所需的 POST JSON 与 Authorization Header。
- Prometheus 专用埋点：指标能力强，但先采用标准 OTLP Trace 保留后端选择空间；业务评测指标仍由离线报告负责。
- 微服务：可以独立扩容检索或 Agent，但当前数据规模和团队规模不支持额外部署与事务复杂度。

## 代价与验证

- Fetch SSE 需要自行处理网络 chunk 边界和 error event，已由前端单元测试覆盖。
- localStorage Token 有 XSS 风险，只作为本地演示方案；生产应采用 HttpOnly Cookie/BFF。
- OTLP 需要外部 Collector 才能落地查看 Trace；启用与装配路径有自动化测试，但本阶段没有部署 Collector。
- Compose 配置解析通过；本机镜像构建被 Docker Hub 网络超时阻断，真实 GitHub Actions Linux runner 已成功构建 API/前端镜像。CI 未启动整套 Compose 服务，不能声称容器运行已验证。
