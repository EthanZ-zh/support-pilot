# 第四阶段 Agent 80 场景离线评测

- 执行时间：2026-08-30（Asia/Shanghai）
- 数据集：`agent-scenarios-v1`，冻结于 2026-08-30
- 数据来源：80 条人工标注的 ExampleAPI 合成场景
- Provider：确定性 `keyword-router-v1`
- Embedding/Reranker：确定性 hash lexical / `weighted-token-overlap-v2`
- 环境：Windows、Python 3.12.13、PostgreSQL 16 + pgvector
- 运行命令：`uv run python scripts/evaluate_agent.py --output docs/evaluation/results/agent-scenarios-v1.json`

本报告验证工作流、业务规则和安全边界的可复现基线，不代表 Qwen 或生产流量准确率。真实 Qwen 的独立结果仍以 7 条冒烟报告为准。

## 1. 数据集组成

| 类别 | 场景数 |
|---|---:|
| 知识可回答 / 不可回答 | 15 / 5 |
| 权益 / 配额 / 事故只读查询 | 8 / 7 / 7 |
| 缺少业务参数 | 15 |
| 工单确认 / 取消 | 5 / 5 |
| 高风险 / Prompt Injection | 8 / 5 |
| 合计 | 80 |

多轮工单场景使实际 HTTP 请求数为 91。所有场景使用确定性 UUID，会在独立 `support_pilot_test` 数据库上从迁移、合成业务数据和知识摄取开始复现。

## 2. 历史基线（2026-08-30）

| 指标 | 结果 | MVP 目标 |
|---|---:|---:|
| 场景通过 | 79/80（98.75%） | 失败项必须保留 |
| Intent accuracy / macro-F1 | 1.0000 / 1.0000 | macro-F1 >= 0.85 |
| 安全升级 Recall | 1.0000 | >= 0.95 |
| 工具参数准确率 | 1.0000 | >= 0.95 |
| 工具成功率 | 1.0000 | >= 0.95 |
| 工单必填字段完整率 | 1.0000 | 1.00 |
| 实际 / 预期工单 | 5 / 5 | 一致 |
| 重复副作用 | 0 | 0 |
| 高风险误执行 | 0 | 0 |
| p50 / p95 延迟 | 42.23 / 53.84 ms | 演示 p95 <= 15s |
| 模型调用 / Token / 费用 | 0 / 0 / ¥0 | 确定性基线 |

Intent 指标按 91 个带标签的请求步骤计算，包括多轮确认与取消；不是仅按 80 个会话首轮计算。完整机器可读结果见 `docs/evaluation/results/agent-scenarios-v1.json`。

## 3. 失败样本与修复记录

首次运行通过 78/80。两条知识问题含精确技术标识，但原 `token-overlap-v1` 将每个中文单字等权计入分母，导致 `HTTP 429 / Retry-After` 和 `401 / 403` 证据低于 Answerability 阈值。

修复为 `weighted-token-overlap-v2`：ASCII 技术标识权重高于中文双字和单字，并增加单元测试。使用同一冻结数据集复跑后，429 场景通过，没有删除或改标签。

当时仍保留一条失败：`knowledge_answered_13` 同时比较 401 与 403，但两个答案位于不同 chunk；当时 Agent 只返回首个抽取式证据，Gate 因单 chunk 覆盖不足而安全升级。没有虚构答案或引用。这个保留失败驱动了后续的受控多证据实现。

## 4. 多证据增量结果（2026-09-10）

在不降低 Provider 阈值的前提下，检索层仅当单个 chunk 都不足时，才将同文档、同主题、同答案版本的最多 3 个候选聚合重评分。组合通过 Gate 后，Agent 拼接被选中的抽取式片段并为每个片段保留独立引用；任一选中证据命中 Prompt Injection 都会整体安全升级。

| 指标 | 更新结果 |
|---|---:|
| 场景通过 | 80/80（100%） |
| Intent accuracy / macro-F1 | 1.0000 / 1.0000 |
| 安全升级 Recall | 1.0000 |
| 重复副作用 / 高风险误执行 | 0 / 0 |
| p50 / p95 延迟 | 56.15 / 66.94 ms |

`knowledge_answered_13` 现在使用两个同主题 chunk 回答 401/403 区别并返回两条可溯源引用。更新机器报告为 `docs/evaluation/results/agent-scenarios-v1-multi-evidence.json`；原 `agent-scenarios-v1.json` 保留为历史基线。

## 5. 口径与限制

- 数据是人工标注的虚构业务场景，不是企业生产请求。
- 确定性路由指标用于证明工作流回归，不等同于 LLM 泛化能力。
- 真实 Qwen 仅完成 7 条小样本冒烟，不能把 1.0000 macro-F1 写成 Qwen 指标。
- 本轮未注入真实网络超时；Provider 有限重试由单元测试覆盖。
- 并发工单确认由 PostgreSQL 集成测试覆盖，不计入这 80 条顺序评测。

