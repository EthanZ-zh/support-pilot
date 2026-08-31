# API 鉴权与错误码

## 认证方式

ExampleAPI v2 使用 `Authorization: Bearer <API_KEY>` 请求头。API Key 只在创建时显示一次，客户不得把完整密钥发送给技术支持。排障时只提供环境、发生时间、错误码、密钥前缀和脱敏 request_id。

## 401 Unauthorized

HTTP 401 表示凭据缺失、格式错误、已撤销或已过期。先确认请求使用 Bearer 方案、生产与测试环境没有混用，并在控制台检查密钥状态。SupportPilot 不会要求客户粘贴完整 API Key。

## 403 Forbidden

HTTP 403 表示身份已识别，但当前租户、角色或 entitlement 不允许访问资源。应查询租户实际权限和功能开关，不能仅凭通用套餐页面推断，也不能通过重试解决权限不足。

