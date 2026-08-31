# API 版本与弃用策略

## 版本选择

ExampleAPI 使用路径版本，例如 `/v2/resources`。SDK 的 major 版本与默认 API 版本分别管理，排障时必须同时记录 SDK 版本和实际请求路径。

## 弃用通知

破坏性变更至少提前九十天发布 deprecation notice，并在版本说明中记录替代接口和停止服务日期。旧文档标记为 superseded 后不得参与默认检索。

## 版本冲突

检索必须使用 product_version 元数据过滤。若客户使用 v2，则 v1 专属参数不能作为答案；无法确认版本时应先澄清，而不是混合不同版本步骤。

