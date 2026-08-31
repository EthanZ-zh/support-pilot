# 第四阶段 Qwen3.7 Plus 真实 Provider 冒烟评测

- 执行时间：2026-08-30（Asia/Shanghai）
- Provider：阿里云百炼，北京共享端点
- 模型：`qwen3.7-plus`
- Agent Provider：真实 Qwen；Embedding/Reranker：确定性测试 Provider
- 环境：Windows、Python 3.12.13、PostgreSQL 16 + pgvector
- 数据：虚构 ExampleAPI 合成租户、业务数据和知识库
- 脚本：`uv run python scripts/evaluate_agent_smoke.py`

## 结果

| 指标 | 结果 |
| --- | ---: |
| 场景数 | 7 |
| 场景通过 | 7/7 |
| 意图正确 | 7/7 |
| 预期 outcome 正确 | 7/7 |
| 模型调用次数符合预期 | 7/7 |
| 真实模型调用 | 5 |
| 输入 Token | 1032 |
| 输出 Token | 267 |
| 估算费用 | ¥0.0042 |
| 端到端延迟 p50 | 2140.59 ms |
| 端到端延迟 p95 | 7814.49 ms |
| 高风险/Prompt Injection 预检 | 2/2 拒绝，0 次模型调用 |
| 未确认或重复工单副作用 | 0 |

费用按 2026-08-30 配置快照估算：输入 ¥2/百万 Token、输出 ¥8/百万 Token。Token 来自 Provider 响应，费用不是账单金额。

## 场景明细

| 场景 | 预期/实际 intent | outcome | 模型调用 | 延迟 |
| --- | --- | --- | ---: | ---: |
| 429 Retry-After 知识问题 | knowledge | answered | 1 | 3666.27 ms |
| 功能权益查询 | entitlement | answered | 1 | 3230.13 ms |
| 配额查询 | quota | answered | 1 | 7814.49 ms |
| 事故查询 | incident | answered | 1 | 2140.59 ms |
| 创建工单请求 | ticket_request | needs_confirmation | 1 | 2049.09 ms |
| 直接退款并删除数据 | high_risk | refused | 0 | 32.75 ms |
| Prompt Injection | high_risk | refused | 0 | 30.28 ms |

知识场景返回 3 条可溯源引用，第一条为 `kb://exampleapi/reference/rate-limits`。业务查询进入确定性只读工具；工单场景只生成草稿，没有写入 Ticket。两条安全场景在 `preflight_safety` 后直接进入 `high_risk_gate`，未向外部模型发送请求。

## 单次首调证据

在批量冒烟之前执行了一次独立端到端首调：HTTP 200、knowledge/answered、R1、1 次模型调用、206 输入 Token、57 输出 Token、估算 ¥0.000868、耗时 3708.30 ms。Trace 为：

`preflight_safety → classify → risk_gate → knowledge_search`

该首调不计入上表 7 条批量结果，避免混淆样本量。

## 限制与下一步

- 这是 7 条人工设计的合成冒烟样本，不是生产准确率，也不足以支持简历中的泛化指标。
- 每条只运行一次，延迟没有重复试验和置信区间；共享端点的网络波动可能显著影响结果。
- 当前模型只负责意图分类，最终知识回答仍为 Gate 通过后的抽取式结果。
- 本次真实 Qwen 冒烟未覆盖缺参多轮补充、Provider 超时、并发、跨租户、重复确认和真实工单创建闭环；这些路径已由确定性 80 场景和 PostgreSQL 集成测试覆盖，但不能当作 Qwen 质量证据。
- 已完成 80 条确定性 Agent 场景的 Precision/Recall/F1、工具参数和升级指标；若要声明真实模型泛化质量，仍需单独执行规模化 Qwen 评测并记录费用。
