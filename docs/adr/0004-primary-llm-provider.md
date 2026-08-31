# ADR 0004：首个真实 LLM Provider 选择

- 状态：Accepted
- 日期：2026-08-30
- 决策：用户选择方案 1，Qwen3.7 Plus 为首个真实 Provider

## 要解决的问题

真实模型需要稳定输出严格结构、正确选择工具参数、支持中文技术支持语境，并把开发与评测成本控制在学生项目可接受范围。业务代码只能依赖 `DecisionProvider`，不能依赖厂商 SDK。

## 方案 1：Qwen3.7 Plus 主模型（推荐）

使用阿里云百炼北京区的 `qwen3.7-plus` 作为首个真实 Provider。官方文档标明其支持 Function Calling、结构化输出和 1M 上下文；北京区不超过 256K 输入时价格为输入 ¥2/百万 Token、输出 ¥8/百万 Token。

- 优点：中国大陆接入和中文能力更适合当前开发环境；严格 JSON Schema 与工具调用满足 Agent 决策；成本低。
- 代价：需要阿里云账号和区域配置；最终简历应描述为 Provider 中立架构，不能写成只会调用百炼。
- 验证：先跑 80 条 Agent 场景，重点测意图、参数、高风险拒绝和空字段；之后用 OpenAI 模型做一轮对照。

## 方案 2：OpenAI GPT-5.6 Terra 主模型

使用 Responses API 的 GPT-5.6 Terra。官方模型比较页将其定位为质量、速度、成本的平衡模型，支持 Function Calling 和 Structured Outputs，价格为输入 $2/百万 Token、输出 $12/百万 Token。

- 优点：Agent 工具生态和结构化输出成熟，国际项目辨识度高；适合作为质量基准。
- 代价：当前开发环境的网络、账号和支付可用性需要先验证，成本高于方案 1。
- 验证：用 GPT-5.6 Luna 跑低成本回归，用 Terra 跑正式评测；不能混用结果口径。

## 方案 3：DeepSeek V4 Flash 主模型

使用官方 OpenAI 兼容接口的 `deepseek-v4-flash`。官方文档标明支持 Tool Calls、JSON Output 和 1M 上下文。

- 优点：成本敏感，接口接入简单，适合大量场景回归。
- 代价：官方 JSON Mode 文档明确提示偶尔可能返回空 content；近期价格规则有变动，接入前需以控制台为准。对本项目最关键的结构稳定性需要额外重试和评测，因此不作为当前首选。
- 验证：专门统计空输出率、Schema 校验失败率、工具参数准确率和重试后成功率。

## 最终决策

选择方案 1：Qwen3.7 Plus 作为首个真实 Provider；保留确定性 Provider 做 CI，第四阶段末再用 GPT-5.6 Terra 对相同评测集做质量对照。生产请求不同时调用两个模型，避免无意义增加延迟和费用。

实现使用北京区 OpenAI 兼容接口和严格 JSON Schema。默认共享 Base URL 只用于开发验证；生产部署应通过配置切换到与 API Key 同一业务空间的专属域名。Provider 超时为 15 秒、最多尝试 2 次，未设置 Key 时返回明确的 503 配置错误。

配置同时识别项目变量 `SUPPORT_PILOT_QWEN_API_KEY` 和百炼标准变量 `DASHSCOPE_API_KEY`。真实 Key 只能存在于被忽略的 `.env` 或操作系统密钥环境中，`.env.example` 必须始终保持空值；一旦 Key 出现在日志、聊天输出或可提交文件中，必须立即撤销并轮换。

模型当前只承担意图分类；业务参数、风险判断、租户授权、Answerability 和写操作确认继续由确定性代码控制。每次成功响应记录模型调用数、输入/输出 Token 和按本 ADR 价格快照估算的人民币成本。真实 Provider 已通过 7 条合成冒烟场景，正式质量结论仍需至少 80 条分层评测。

官方资料：

- Qwen3.7 Plus：https://help.aliyun.com/zh/model-studio/qwen3-7-plus
- 百炼地域与 Base URL：https://help.aliyun.com/zh/model-studio/beijing-access-information
- 百炼结构化输出：https://help.aliyun.com/zh/model-studio/qwen-structured-output
- OpenAI 模型比较：https://developers.openai.com/api/docs/models/compare
- DeepSeek 定价与模型：https://api-docs.deepseek.com/quick_start/pricing/
- DeepSeek JSON Mode：https://api-docs.deepseek.com/guides/json_mode/
