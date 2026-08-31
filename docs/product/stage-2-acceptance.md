# 第二阶段：确定性业务基线验收

状态：已实现并在本地隔离 PostgreSQL 上验证  
验证日期：2026-08-29

本阶段只验收不依赖 LLM 的业务闭环。RAG、LangGraph、JWT、人工接管 API 和前端不属于本阶段完成声明。

## 1. 交付范围

- [x] FastAPI、Pydantic、SQLAlchemy 2、Alembic 和 PostgreSQL 项目可运行。
- [x] 租户、用户、套餐、entitlement、额度、服务组件、事故、支持请求、工单、幂等记录和审计模型已迁移。
- [x] 提供固定 UUID 的合成 `ExampleAPI` fixture，名称明确标注为合成数据。
- [x] 提供 entitlement、额度、事故查询和工单创建的结构化确定性路由。
- [x] 风险由代码根据 intent 决定，调用者不能提交自定义风险等级。
- [x] R3 请求不会调用写工具，只返回拒绝并写审计。
- [x] 工单状态转换规则已定义并有单元测试；人工接管和状态变更 API 留到第五阶段。

## 2. 行为验收证据

| 编号 | 行为 | 自动化证据 |
|---|---|---|
| S2-AC-01 | Alpha 租户查询 `bulk_export`，确定性返回 Starter 套餐未启用 | `test_entitlement_query_uses_tenant_data_and_redacts_message` |
| S2-AC-02 | Alpha 用户查询 Beta 数据被拒绝且产生 denied 审计 | `test_cross_tenant_query_is_denied_and_audited` |
| S2-AC-03 | 额度剩余值由代码计算，不交给模型 | `test_quota_is_calculated_by_code` |
| S2-AC-04 | 事故查询区分“确认匹配”和“未发现但不代表正常” | `test_incident_query_distinguishes_match_from_no_match` |
| S2-AC-05 | 相同幂等键和载荷重放返回同一工单；不同载荷冲突 | `test_ticket_creation_is_idempotent_and_rejects_changed_payload` |
| S2-AC-06 | 两个并发请求只创建一个工单 | `test_concurrent_ticket_retries_create_one_side_effect` |
| S2-AC-07 | 工单缺少 `Idempotency-Key` 时拒绝写入 | `test_ticket_creation_requires_idempotency_key` |
| S2-AC-08 | 高风险动作不执行、不创建工单并写 denied 审计 | `test_high_risk_action_is_refused_without_ticket` |
| S2-AC-09 | 缺少可信用户上下文时返回 401 | `test_request_requires_authenticated_user` |
| S2-AC-10 | 消息和嵌套诊断上下文中的 Secret 被脱敏 | `test_secrets_are_redacted_recursively` 及 entitlement 集成测试 |

## 3. 验证命令

```powershell
docker compose up -d postgres postgres-test
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run alembic upgrade head
uv run alembic check
```

验收必须保留命令实际输出。本文件中的勾选表示上述实现存在，不替代测试结果。

本次本地验证结果：

- Python：uv 管理的 CPython 3.12.13；
- 数据库：Docker `postgres:16-alpine` 独立测试容器；
- 测试：`18 passed`；
- 语句覆盖率：`96%`（579 条语句，22 条未覆盖）；
- 迁移：`downgrade base → upgrade head` 通过，`alembic check` 无模型漂移；
- 静态检查：Ruff 与 strict mypy 通过；
- 运行冒烟：真实 Uvicorn 进程连接开发 PostgreSQL，entitlement 请求返回 HTTP 200 和确定性结果；
- 已知警告：当前 FastAPI/Starlette `TestClient` 对 `httpx` 发出迁移到 `httpx2` 的上游弃用提示，不影响本次测试结果，后续依赖升级时处理。

## 4. 与产品验收标准的对应关系

- AC-03：entitlement 与 quota 由数据库和确定性代码判断，已覆盖。
- AC-04：跨租户访问拒绝并审计，已覆盖；完整 JWT 尚未实现。
- AC-05：事故匹配的确定性部分已覆盖。
- AC-06：持久化前 Secret 脱敏已覆盖；自然语言多轮补参尚未实现。
- AC-07：顺序重试、不同载荷和真实 PostgreSQL 并发重试已覆盖。
- AC-09：R3 自动执行数量为零，已覆盖当前注册路由。
- AC-11：状态转换领域规则已覆盖；RBAC 接管接口尚未实现。

## 5. 未完成与风险

- `X-User-Id` 是演示身份头，不能防伪；真实认证和完整 RBAC 属于第五阶段。
- 当前工单只有创建能力；查询、领取、状态迁移和反馈 API 尚未实现。
- 当前工具调用没有超时/重试封装，因为全部是本地数据库调用；外部工具接入时必须补齐。
- 未进行吞吐和 p95 延迟测试，不能声称生产性能。
- 只验证 PostgreSQL 16；尚未加入 pgvector，第三阶段 RAG 再引入。
- 测试依赖 Docker；Docker 不可用时只能运行单元测试，不能声称数据库行为已验证。
