# 第七阶段工程质量验收

状态：通过；完整 Compose 运行仍是明确限制

## 已实现

- [x] OpenTelemetry FastAPI 与 SQLAlchemy 自动埋点，通过 OTLP/HTTP 可配置导出；
- [x] Telemetry 默认关闭，不依赖 Collector 才能启动业务；
- [x] 后端 Dockerfile 使用非 root 用户和 frozen lock；
- [x] 前端多阶段 Dockerfile 只交付 Nginx 静态产物，并关闭 SSE 代理缓冲；
- [x] Compose 编排 API、前端、开发库和隔离测试库，依赖 healthcheck 启动；
- [x] GitHub Actions 分离 backend、frontend、container 三条作业；
- [x] CI 包含 Ruff、strict mypy、全量测试/覆盖率、迁移升级/漂移检查、前端 lint/test/build 和镜像构建；
- [x] PowerShell 演示脚本覆盖知识回答、引用、工单确认、人工认领与状态推进；
- [x] Alembic 在隔离测试库完成 downgrade/upgrade 往返。

## 验证证据（2026-08-31）

- 后端：67 passed，语句覆盖率 93%，Ruff 与 strict mypy 通过；
- 前端：4 passed，ESLint 和 TypeScript/Vite 生产构建通过；
- 迁移：`0006 → 0005 → 0006` 成功，`alembic check` 无漂移；
- Compose：`docker compose config --quiet` 成功，解析出 `postgres-test/postgres/api/frontend`；
- 真实本地演示：知识 `answered`、3 条引用、工单推进到 `in_progress`；
- 容器：本地两次 build 因 Docker Hub token 地址 TCP 超时失败；真实 GitHub Actions Linux runner 随后成功构建 API 和前端镜像。

## 剩余风险

- API/前端镜像未在本机完成 build，CI 也未启动整套 Compose 服务；仍需执行并记录 `docker compose up -d` 的运行态验证；
- GitHub Actions 已在真实仓库 runner 执行；首次运行暴露 Alembic 数据库端口配置错误，修复后由配置回归测试锁定；
- OTel 装配路径经过 mock 测试，尚未连接真实 Collector 查看 Span；
- 当前只有 Trace，没有服务级 Prometheus 指标、日志关联和告警规则；
- Starlette TestClient 对 httpx 的弃用告警来自依赖组合，不影响当前测试，升级前应做兼容性验证。
