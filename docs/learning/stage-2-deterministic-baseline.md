# 第二阶段学习说明：确定性业务基线

## 1. 架构变化

项目从产品文档变为可运行的模块化单体：

```text
HTTP / FastAPI
    ↓ 解析 Header 与 discriminated union
Application / SupportService
    ↓ 编排授权、查询、事务和审计
Domain / risk、RBAC、状态机、脱敏、哈希规则
    ↓
Infrastructure / SQLAlchemy Repository + PostgreSQL
```

核心原则是：LLM 以后可以选择调用哪个已授权工具，但不能决定租户归属、功能是否开启、额度数值、状态转换是否合法或写操作是否重复。

## 2. 一次 entitlement 请求的完整链路

1. 客户向 `POST /api/v1/support/resolve` 提交 `intent=entitlement`、租户和功能代码。
2. FastAPI 用 discriminated union 校验输入，未知字段、非法代码和缺失参数返回 422。
3. `get_current_user` 根据合成 `X-User-Id` 加载活动用户。
4. `SupportService` 创建脱敏后的 `SupportRequestRecord`，并由 intent 固定风险为 R1。
5. `can_access_tenant` 以确定性规则检查调用者是否属于目标租户；内部支持角色可跨租户处理。
6. Repository 查询当前生效 entitlement 和套餐，Application 组装最小响应。
7. 同一事务更新请求状态并写 `AuditEvent`，提交后返回 `request_id` 和 `trace_id`。

## 3. 工单幂等链路

1. 客户提交 R2 `ticket_request`，必须带 `Idempotency-Key`。
2. 服务对除 `session_id` 外的规范化请求计算 SHA-256 hash。
3. PostgreSQL 尝试插入复合主键 `(scope, key)` 的幂等记录：
   - 插入成功：当前请求拥有写入权，创建工单并在同一事务标记成功；
   - 冲突且 hash 相同：等待原事务后返回已有工单；
   - 冲突且 hash 不同：返回 409，不覆盖已有结果。
4. `RETURNING` 用于判断当前事务是否真的插入记录，不能依赖不同驱动表现不一致的 `rowcount`。
5. 工单、幂等结果和审计在同一事务提交，避免“工单成功但幂等记录丢失”。

## 4. 遇到的问题与修复

- 打包失败：`pyproject.toml` 引用了不存在的 README；补齐 README 后重新构建。
- ORM 关联表失败：`Table` 需要 Core `Column`，不能使用 ORM `mapped_column`；修正后应用可导入。
- Docker 端口失败：Windows 保留了 `55432`；检查排除范围后统一切换到 `54329`。
- Seed 外键失败：仅保存 UUID 的子对象无法让 Unit of Work 推导对象顺序；按套餐、租户、业务数据分段 flush。
- 幂等误判：psycopg 的 `rowcount` 不适合判断 `ON CONFLICT` 插入归属；改为 `RETURNING`，顺序和并发测试均通过。
- 测试数据风险：最初测试复用了开发数据库；改为端口 `54330` 的独立临时测试服务，并校验数据库名必须为 `support_pilot_test`。

## 5. 技术取舍

- 现在选择同步 SQLAlchemy，是为了降低事务和并发测试的认知负担；没有负载证据时不提前引入 async。
- 使用 PostgreSQL 专属 `ON CONFLICT`，换来明确的并发幂等语义；代价是该路径不支持 SQLite。
- 目前直接使用合成 `X-User-Id`，只验证授权规则，不伪装成完整认证；JWT 留到安全阶段。
- 先做 discriminated union 的结构化 intent，验证业务能力；自然语言意图识别留给 Agent 阶段。

## 6. 你需要掌握的知识点

- Pydantic discriminated union 如何让不同 intent 拥有不同必填字段；
- SQLAlchemy Session、flush、commit 和数据库事务之间的区别；
- 唯一约束为什么是幂等的最终防线，以及 `ON CONFLICT` 如何处理并发；
- 租户隔离为什么必须在工具内部校验，不能只依赖 Prompt；
- Alembic migration 与 ORM model 为什么需要用 `alembic check` 保持一致；
- 审计事件、应用日志和 trace 的用途有何不同；
- 为什么输入进入数据库、日志或未来模型前都要脱敏。

## 7. 面试表达

### 30 秒

“我先没有接 LLM，而是用 FastAPI、SQLAlchemy 和 PostgreSQL实现确定性业务基线。所有租户权限、额度、事故窗口和工单副作用都由代码与数据库约束决定。工单使用作用域幂等键、规范化请求 hash、`ON CONFLICT RETURNING` 和事务，真实并发测试证明两个重试只创建一个工单。”

### 3 分钟

沿一次请求讲清 API Schema、身份上下文、租户规则、Repository 查询、事务审计和响应，再对比 ticket 分支的 R2 风险、幂等记录及冲突处理。最后说明当前身份头、缺少完整工单状态 API 和未做负载测试等限制。

### 深入追问

- 如果第一个工单事务执行很慢，第二个相同幂等请求会发生什么？
- 为什么不能先创建工单、提交后再写幂等记录？
- 同一个幂等键但载荷不同为什么必须返回冲突？
- 仅在 API 路由检查 `tenant_id` 有什么绕过风险？
- `flush()` 成功是否意味着数据已经对其他事务可见？
- 如果以后改成异步 SQLAlchemy，业务规则和测试应如何保持不变？

