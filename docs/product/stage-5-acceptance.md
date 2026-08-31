# 第五阶段安全闭环验收

状态：MVP 范围通过

## 1. 请求链路

```text
email/password → Argon2id verify → short-lived JWT
  → Bearer signature/issuer/audience/expiry validation
  → current DB user role + tenant drift check
  → tenant RBAC
  → ticket read / claim / transition / feedback
  → idempotency + expected_version + state machine
  → TicketTransition or HumanFeedback + AuditEvent
```

## 2. 已实现验收项

- [x] 默认要求 Bearer JWT，演示身份头默认关闭；
- [x] 密码只保存 Argon2id 哈希，JWT 密钥只从环境变量读取；
- [x] Token 校验签名、过期、issuer、audience、角色和租户漂移；
- [x] 客户只能读取本租户工单，跨租户拒绝并审计；
- [x] 只有 `support_agent` 可以领取和迁移工单；
- [x] 工单领取、合法状态迁移和版本递增在事务内完成；
- [x] 非法迁移、旧版本并发提交和非 assignee 修改返回 409/403；
- [x] 领取、迁移和反馈都要求幂等键，重放不重复产生副作用；
- [x] 人工反馈关联 Ticket 与 AgentRun，Secret 脱敏且不会自动发布知识；
- [x] 用户消息和首个检索证据中的基础 Prompt Injection 在自动回答/工具前阻断；
- [x] 认证失败、越权、幂等冲突、版本冲突和状态机拒绝均有审计证据。

## 3. 明确限制

- Prompt Injection 是规则 + 架构隔离，不代表能检测所有自然语言攻击；
- 没有 Refresh Token、MFA、登录速率限制或集中撤销列表；
- HS256 适合模块化单体演示，真实企业部署应接 OIDC/JWKS；
- 人工反馈只进入候选改进数据，不自动修改权威知识库。

## 4. 验证证据

- `pytest --cov=support_pilot`：62 passed，语句覆盖率 93%；
- JWT：登录、错误密码、篡改、过期、角色漂移和默认禁用旧身份头均有测试；
- RBAC：客户跨租户读取与领取被拒绝并审计；
- 状态机：非法转换和旧 version 提交为 0 成功；
- 幂等：顺序重放与两个并发领取只生成一次 TicketTransition；
- 反馈：同 Key 重放、换 Key 冲突、Secret 脱敏和唯一记录均通过；
- Prompt Injection：用户输入在模型前拦截，恶意首证据不进入自动回答；
- `ruff`、`mypy` 与 Alembic 正向迁移检查通过。
