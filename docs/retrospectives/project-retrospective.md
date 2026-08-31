# SupportPilot 项目复盘

## 做对了什么

- 先构建确定性业务基线再接模型，避免把权限、额度、状态迁移交给 LLM 猜；
- 每一阶段形成运行增量和机器结果，而不是一次生成大量空接口；
- 将 deterministic、本地 BGE、真实 Qwen 的评测口径严格分开；
- 通过幂等、version、唯一约束、行锁和审计把“创建工单”做成真实低风险写入；
- 保留失败样本：401/403 多证据覆盖不足时升级人工，没有调低 Gate 迎合指标。

## 实现中发现的问题

1. BGE CrossEncoder 已返回概率，重复 sigmoid 导致无答案样本全被放行；加入负例后才暴露并修复。
2. 中文单字稀释 HTTP 状态码等技术标识，确定性 Reranker 改为加权词项后修复 429 场景，并用原检索集回归。
3. TypeScript 7 与 typescript-eslint peer range 不兼容，依据实际安装错误降到 6.0 系列，而不是使用 `--force` 绕过。
4. SSE 网络 chunk 不等于事件边界，前端增加残片 buffer 和跨 chunk 测试。
5. Dockerfile/Compose 配置通过解析，但两次真实 build 都在 Docker Hub 鉴权地址超时，未把环境失败伪装成容器交付成功。

## 当前技术债

- 知识集小且同源，Gate 阈值没有独立校准集；
- 答案以抽取式为主，缺少多证据聚合、逐主张引用和忠实度评测；
- Agent 节点级 checkpoint 尚未持久化，只有会话与运行最终状态；
- JWT 无 refresh/MFA/revocation，浏览器使用 localStorage；
- 工单队列无游标分页、搜索和实时推送，前端无 Playwright E2E；
- OTel 未连接 Collector，容器镜像未因网络问题完成本地 build。

## 下一轮优先级

P0：网络恢复后完成容器 build/up、浏览器真实 E2E 和演示录像。  
P1：拆分 RAG calibration/test，增加多 chunk 证据覆盖与逐主张引用评测。  
P2：OIDC/BFF、SSE Abort/恢复、队列分页和 OTel Collector/指标/日志关联。  
P3：只有在压测证明需要时，再拆检索或 Agent 服务。
