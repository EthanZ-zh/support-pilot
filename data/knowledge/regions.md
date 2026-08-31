# 区域、端点与数据驻留

## 区域端点

新加坡区域使用 `https://ap-southeast-1.api.example.invalid`，法兰克福区域使用 `https://eu-central-1.api.example.invalid`。示例域名完全虚构，不提供真实服务。

## 数据驻留

租户创建后确定主要数据区域。普通 API 请求不会自动跨区域复制客户资源；是否允许变更区域属于高风险人工流程，SupportPilot 不会自动执行。

## 区域排障

报告延迟或超时时必须提供实际 endpoint、区域和时间。查询事故时以请求命中的区域为准，不能只使用用户所在地推断。

