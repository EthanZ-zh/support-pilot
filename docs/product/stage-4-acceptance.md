# 第四阶段 Agent 验收

状态：MVP 范围通过，保留一个非安全性质量失败

## 1. 已验收能力

- Provider 中立的 LangGraph 有限 DAG，模型只负责意图判断；
- 知识检索、Answerability Gate、租户只读工具和工单草稿接入同一工作流；
- 缺参和待确认状态通过 `AgentConversation` 跨请求恢复；
- 工单确认使用客户端 Key 哈希与稳定内部幂等键，顺序重放和并发确认无重复副作用；
- 高风险和基础 Prompt Injection 在模型与工具前拦截；
- AgentRun、会话状态、Trace 和审计记录持久化；
- 80 条版本化场景、91 次请求的离线评测可从独立测试库复现。

## 2. 验收证据

- 80 场景：79/80 通过，Intent macro-F1 1.0000，安全升级 Recall 1.0000；
- 工具参数准确率、工具成功率、工单字段完整率均为 1.0000；
- 高风险误执行和重复副作用均为 0；
- 46 个既有自动化测试以及新增评测 Schema/指标测试；
- 真实 Qwen 7 条冒烟全部通过，但不外推为模型准确率。

详细结果见：

- [80 场景评测](../evaluation/stage-4-agent-evaluation.md)
- [Qwen 冒烟评测](../evaluation/stage-4-qwen-smoke-evaluation.md)
- [可恢复会话 ADR](../adr/0005-recoverable-conversation-and-ticket-confirmation.md)

## 3. 明确边界

- “401 与 403 比较”需要跨两个 chunk 的受控答案合成，当前安全升级；
- 领域会话状态已恢复，但没有 LangGraph 任意节点级 checkpoint；
- Prompt Injection 仍是基础规则，完整输入分层与认证授权属于第五阶段；
- 第四阶段验收时身份仍使用 `X-User-Id` 演示头；第五阶段已替换为默认 Bearer JWT。

这些限制不阻断第四阶段 MVP：持久状态、有限重试、失败降级、工具调用和工单闭环已具备可运行证据。节点级 checkpoint 只有在引入真正 interrupt 节点后才有业务必要，不为技术名词提前维护第二套状态。
