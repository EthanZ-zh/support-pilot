# API 限流与月度额度

## 429 与响应头

HTTP 429 表示短期限流。响应包含 `X-RateLimit-Limit`、`X-RateLimit-Remaining`、`X-RateLimit-Reset` 和 `Retry-After`。客户端应以 Retry-After 为准，不要立即并发重试。

## 退避策略

对可重试请求使用带随机抖动的指数退避，并设置最大重试次数。非幂等写请求只有携带稳定 Idempotency-Key 时才允许自动重试。

## 月度额度

月度 quota 与瞬时 rate limit 是不同概念。剩余额度必须查询租户最新 QuotaSnapshot，由确定性代码计算；不能让模型依据文档猜测客户已用量。

