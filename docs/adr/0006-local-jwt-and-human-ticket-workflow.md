# ADR 0006：本地 JWT、RBAC 与人工工单闭环

状态：已接受  
日期：2026-08-30

## 背景

第二至第四阶段使用合成 `X-User-Id` 只验证领域授权，不能防止身份伪造。第五阶段还需要支持人员领取工单、有限状态迁移、并发版本冲突和人工反馈，所有 R2 写操作必须幂等并可审计。

## 决策

采用用户选择的本地 JWT 方案：

- `POST /api/v1/auth/login` 使用合成邮箱和 Argon2id 密码哈希验证；
- 签发 30 分钟 HS256 Access Token，校验 `sub/role/iss/aud/iat/nbf/exp/jti`；
- `tid` 绑定租户用户，内部角色允许为空；数据库角色、租户或状态变化后旧 Token 立即失效；
- 签名密钥最少 32 字符，只从 `SUPPORT_PILOT_JWT_SECRET` 读取；
- `X-User-Id` 默认关闭，只能通过显式测试配置启用；
- 客户只能查看本租户工单，`support_agent` 才能领取和迁移；内部角色可提交反馈；
- 领取把 `open → triaged` 与 assignee 写入同一事务；后续状态遵守有限状态机；
- 写 API 同时要求 `Idempotency-Key` 和 `expected_version`，顺序/并发重放不重复产生 Transition 或 Feedback；
- 成功、越权、非法转换、版本冲突和认证失败都写脱敏审计。

密码哈希与 JWT 库遵循 [FastAPI 官方安全教程](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) 推荐的 `pwdlib` Argon2 与 PyJWT 组合。JWT 只签名、不加密，因此不放密码、Secret 或业务详情。

## 替代方案

- Keycloak/OIDC：更接近企业 IdP，但增加容器、Realm 配置和演示失败面；当前业务闭环不需要。
- Auth0/Clerk：接入快，但依赖外部账户、网络和费用，不利于离线复现。

## 代价与限制

- HS256 由单个服务持有共享密钥，不适合多团队密钥分发；生产应迁移 OIDC/JWKS。
- MVP 没有 Refresh Token、MFA、找回密码、速率限制和 Token 撤销表。
- 演示账号和密码完全是合成数据，只用于本地项目；不得复用真实密码。

