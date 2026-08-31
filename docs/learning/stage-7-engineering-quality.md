# 第七阶段学习说明：可观测性、CI 与可复现交付

## 30 秒讲法

“我把 SupportPilot 的业务闭环变成可重复验证的工程交付：FastAPI 和 SQLAlchemy 通过可开关的 OpenTelemetry/OTLP 产生 Trace，GitHub Actions 分开验证后端、前端和容器，Alembic 做升级、降级和模型漂移检查；一键演示脚本真实走完引用回答到人工工单推进。本地 Docker Hub 连接失败后，我用真实 GitHub runner 验证了镜像构建，同时把整套 Compose 运行保留为未验证边界。”

## 3 分钟链路

1. 应用启动读取 Settings；仅当 `OTEL_ENABLED=true` 时创建 Resource、TracerProvider、BatchSpanProcessor 和 OTLP exporter。
2. FastAPI instrumentation 记录请求 Span，SQLAlchemy instrumentation 记录数据库调用；业务 AgentRun 的 `trace_id` 仍用于领域审计，两者承担不同目的。
3. Compose 等待 PostgreSQL healthy 后，让 API 迁移、播种合成数据、摄取确定性知识并启动；Nginx 再代理 API/SSE。
4. 后端 CI 用独立 `support_pilot_test`，先升级迁移和检查模型漂移，再执行全量测试；前端独立执行 lint/test/build。
5. `demo.ps1` 不修改高风险资源，只使用合成账号，验证客户知识问答、显式工单确认、支持人员认领和合法迁移。

## 高频追问

- 为什么 OTel 默认关闭？——无 Collector 时持续导出会产生噪声和资源消耗；显式启用更符合可控配置。
- Agent trace_id 与 OpenTelemetry trace_id 为什么不合并？——前者是持久业务审计标识，后者是进程/服务调用链；后续可通过 Span attribute 关联，不应先删除任何一方。
- 为什么迁移要 downgrade 再 upgrade？——只做 upgrade 无法发现回滚脚本缺失；往返验证至少证明最近迁移在隔离库可逆。
- 为什么 CI 要拆 job？——依赖和失败域不同，前端不应等待 PostgreSQL，容器失败也不应掩盖业务测试结果。
