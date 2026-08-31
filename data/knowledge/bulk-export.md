# 批量导出 API 与套餐权限

## 可用套餐

`bulk_export` 功能仅对 Pro 和 Enterprise 套餐开放，Starter 默认不具备该 entitlement。租户可能存在试用或人工 override，因此最终结论必须查询当前租户 entitlement。

## 创建导出任务

调用 `POST /v2/exports` 创建异步任务，并携带 Idempotency-Key。成功后轮询任务状态，完成后下载短时有效的签名 URL。不要重复创建相同导出任务。

## 权限错误

如果 API 返回 403，先确认调用角色拥有 `exports:write`，再确认租户启用了 `bulk_export`。SupportPilot 只能查询或生成升级工单，不能自动修改套餐和权限。

