# ADR-0001：确定性基线采用同步 SQLAlchemy 的模块化单体

状态：Accepted  
日期：2026-08-29

## 背景

第二阶段需要先证明租户隔离、entitlement、额度、事故、工单幂等和审计等确定性规则。在这些规则稳定前引入 Agent 或拆分服务会扩大调试面，也无法证明 LLM 之外的业务闭环是否可靠。

## 决策

- 使用 Python 3.11+、FastAPI、Pydantic、SQLAlchemy 2、Alembic 和 PostgreSQL 16。
- 使用模块化单体，依赖方向为 `API → Application → Domain`；Application 在当前阶段通过 Repository/Session 访问 Infrastructure。
- 使用同步 SQLAlchemy 与 psycopg。FastAPI 会把同步路由放在线程池中执行。
- 使用 PostgreSQL `INSERT ... ON CONFLICT ... RETURNING`、复合主键和事务实现工单幂等。
- 开发数据库与测试数据库分离；测试数据库使用独立容器和临时文件系统。
- 身份暂由合成 `X-User-Id` 传入，只用于验证领域授权；JWT/RBAC 完整实现留到安全闭环阶段。

## 备选方案

### 方案 A：同步 SQLAlchemy（已选择）

解决当前事务、约束和查询需求，调试路径短，适合学习和演示。代价是高并发 I/O 下线程池和连接池需要容量规划，未来若测得数据库等待成为瓶颈，可能需要改为异步。

### 方案 B：异步 SQLAlchemy

能够在大量并发等待数据库时减少线程占用，但事务 fixture、调用链和调试更复杂。当前没有负载证据证明这项复杂度有价值，因此不选择。

### 方案 C：SQLModel 或直接 ORM 写在路由中

初始代码更少，但 API Schema、领域规则和持久化模型容易耦合，后续 Agent 工具复用困难，因此不选择。

## 后果

正面影响：

- 业务规则可以在不启动模型的情况下测试；
- PostgreSQL 约束、事务和并发幂等有真实集成测试证据；
- 后续 Agent 只编排已验证的 Application use case，不直接操作数据库。

限制：

- 这不是严格六边形架构，Application 仍依赖 SQLAlchemy Session；若未来需要替换数据库，再引入 Protocol/UoW 抽象。
- 当前鉴权头不可用于生产，任何真实部署前必须替换为可信身份认证。
- 当前没有负载测试，不能宣称同步访问已满足生产吞吐。

## 验证方式

- Ruff 和 mypy 检查分层后的代码；
- Alembic `upgrade head` 与 `check` 验证迁移和模型一致；
- PostgreSQL 集成测试验证租户隔离、事故窗口、幂等重放、不同载荷冲突和两个并发请求只创建一个工单。

