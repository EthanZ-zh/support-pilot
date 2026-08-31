# Webhook 签名验证

## 签名输入

ExampleAPI v2 在 `X-ExampleAPI-Signature` 中发送十六进制 HMAC-SHA256 签名。签名输入是原始 HTTP request body 字节；JSON 重新序列化、改变空格或字段顺序都会导致验证失败。

## 验证步骤

使用 endpoint secret 对原始 body 计算 HMAC-SHA256，再用常量时间比较函数核对签名。必须先验证签名再解析或处理事件。endpoint secret 不得进入日志、工单或向量库。

## 时间戳与重放

`X-ExampleAPI-Timestamp` 与签名共同验证。默认只接受五分钟内的事件，并保存 event_id 防止重复处理。时间偏差过大时先校准服务器时钟。

