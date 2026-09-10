# 第三阶段 RAG 离线评测报告

- 运行时间：2026-08-30（Asia/Shanghai）
- 校准集：`data/evaluation/retrieval_calibration_cases.json`
- 独立测试集：`data/evaluation/retrieval_test_cases.json`（实现冻结后首次运行）
- 数据性质：人工标注的合成 ExampleAPI 问题，不含真实企业数据
- 总样本：60（50 个可答检索正例，10 个无答案/越界负例）
- K：5
- 数据库：PostgreSQL 16 + pgvector 0.8.6 镜像
- 执行设备：本地 CPU

## 校准集历史结果

| Provider | Embedding | Reranker | Recall@5 | MRR | nDCG@5 | Answerability P/R/F1 | 错误数 |
|---|---|---|---:|---:|---:|---:|---:|
| deterministic | hash-lexical-v1 | weighted-token-overlap-v2 | 1.000 | 1.000 | 1.000 | 1.000 / 1.000 / 1.000 | 0 |
| local_bge | BAAI/bge-small-zh-v1.5 | BAAI/bge-reranker-base | 1.000 | 1.000 | 1.000 | 1.000 / 1.000 / 1.000 | 0 |

Answerability 混淆矩阵（两种 Provider 本次相同）：TP=50、FP=0、FN=0、TN=10。

## 独立测试集结果

2026-09-10 将原 60 条数据固定为 calibration，新增 ID 不重叠的 30 条 holdout（20 个可答、10 个不可答）。多证据实现在首次 holdout 前已提交冻结，没有根据 holdout 失败调整阈值。

| Provider | Recall@5 | MRR | nDCG@5 | Answerability P/R/F1 | TP/FP/FN/TN |
|---|---:|---:|---:|---:|---:|
| deterministic | 1.000 | 1.000 | 1.000 | 1.000 / 0.800 / 0.889 | 16/0/4/10 |
| local_bge | 1.000 | 0.975 | 0.982 | 1.000 / 0.950 / 0.974 | 19/0/1/10 |

两种 Provider 在 holdout 上都没有误放行。`local_bge` 剩余的一条失败是 `holdout-auth-01`，系统因相关性不足安全升级；这是可答性漏放，不是无证据回答。

## 可复现命令

```powershell
uv run python scripts/ingest_knowledge.py --provider deterministic
uv run python scripts/evaluate_retrieval.py --provider deterministic

$env:HF_HOME = 'D:\model-cache\support-pilot\huggingface'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
uv run python scripts/ingest_knowledge.py --provider local_bge
uv run python scripts/evaluate_retrieval.py --provider local_bge
```

默认评测命令现在使用独立测试集；如需重现历史校准结果，显式传入 `--dataset data/evaluation/retrieval_calibration_cases.json`。

## 评测过程中发现并修复的问题

1. `CrossEncoder.predict()` 已输出 0–1 概率，Provider 再做 sigmoid 会把所有低相关分数抬到约 0.5，造成 10/10 无答案负例误放行。移除重复 sigmoid 后，真实 BGE 的 FP 从 10 降为 0。
2. 确定性词项重排与 BGE 分数量纲不同。统一阈值 0.35 导致 3 个正例漏拒答；为 Provider 声明独立阈值后，确定性基线使用 0.28，BGE 使用 0.35。
3. 只使用 50 个正例时，检索满分掩盖了 Gate 缺陷。加入 10 个无答案/越界负例后才发现上述错误。
4. 第四阶段 80 场景发现技术标识被中文单字稀释，确定性重排改为加权词项重叠；使用原 60 条检索集复跑后各项指标和 10/10 负例拒答保持不变。机器结果见 `docs/evaluation/results/retrieval-deterministic-v2.json`。

## 如何解读

- 满分主要说明当前实现能稳定区分这 10 篇合成文档及其对应问题，证明链路可运行、可回归，不是生产准确率。
- 每个正例只标注一个相关 `source_uri`，因此 nDCG 的难度有限；后续需要多相关片段、近似干扰文档和跨版本冲突。
- 目前可验证“返回引用属于标注相关来源”，但尚未生成最终答案，因此不能宣称回答忠实度或逐主张引用正确率已达标。
- calibration/test 已拆分，holdout 结果也表明同源校准集满分不能代表改写问题的泛化。数据仍是小规模合成集，需继续扩大公开数据和人工标注样本。

## 下一轮评测缺口

- 增加拼写错误、口语、省略上下文、跨语言和相似错误码；
- 增加过期版本、套餐互斥、官方文档冲突和 Prompt Injection 文档；
- 将一个问题标注到多个相关 chunk，分别评估 chunk-level 与 document-level 指标；
- Agent 阶段增加忠实度、逐主张引用、工具参数和端到端升级指标；
- 记录 p50/p95 延迟、模型调用次数和 CPU/内存成本。
