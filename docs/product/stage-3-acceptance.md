# 第三阶段：混合 RAG 验收

状态：已实现并在本地 PostgreSQL、pgvector 与真实本地 BGE 上验证  
验证日期：2026-08-30

本阶段验收知识摄取、检索、重排、引用和 Answerability Gate。最终自然语言答案生成、LangGraph、JWT、人工接管和前端不属于本阶段完成声明。

## 1. 交付范围

- [x] `pgvector` 扩展、知识文档/分块/多 Provider 向量模型及 Alembic 迁移。
- [x] manifest 驱动的 Markdown 摄取、标题路径分块、checksum、稳定 UUID 和重复摄取。
- [x] PostgreSQL `tsvector` 关键词召回与 pgvector cosine 向量召回。
- [x] published、生效时间、产品版本和套餐元数据过滤。
- [x] RRF 融合、Provider 隔离的 Reranker、稳定 Citation 和 Answerability Gate。
- [x] deterministic CI Provider 与本地 BGE Provider 的向量共存。
- [x] 50 个检索正例及 10 个 Answerability 负例的离线评测。
- [x] 模型默认缓存和本次实际下载均位于 D 盘。

## 2. 行为验收证据

| 编号 | 行为 | 自动化或运行证据 |
|---|---|---|
| S3-AC-01 | 摄取 10 篇合成文档并产生 30 个分块 | `scripts/ingest_knowledge.py` 本地运行输出 |
| S3-AC-02 | 重复摄取不重复文档/向量，多 Provider 向量不互相覆盖 | `test_ingestion_is_repeatable_and_preserves_multiple_provider_embeddings` |
| S3-AC-03 | 关键词与向量候选通过 RRF 融合 | `test_rrf_rewards_a_chunk_found_by_both_retrievers` |
| S3-AC-04 | 版本和套餐过滤发生在检索 SQL 中 | `test_hybrid_search_returns_traceable_citation_and_applies_filters` |
| S3-AC-05 | 命中返回 chunk、来源、标题路径、版本和摘录 | RAG 集成/API 测试 |
| S3-AC-06 | 低相关证据拒答，冲突官方证据可识别 | `test_answerability_gate_rejects_low_relevance` 与冲突测试 |
| S3-AC-07 | API 暴露 Provider、Gate 和证据 | `test_knowledge_search_api_returns_provider_and_evidence` |
| S3-AC-08 | 50 个正例跟踪 Recall@5/MRR/nDCG@5 | 第三阶段离线评测报告 |
| S3-AC-09 | 10 个负例跟踪 Answerability P/R/F1 | 第三阶段离线评测报告 |
| S3-AC-10 | 两个真实 BGE 模型可以完全离线从 D 盘加载 | `HF_HUB_OFFLINE=1` 模型加载和评测 |

## 3. 本地验证结果

- 测试：完整测试套件 `28 passed`；
- 静态检查：Ruff 与 strict mypy 通过；
- 迁移：开发库和全新测试库升级到 `0002`，模型漂移检查通过；
- 摄取：10 篇、30 chunk，deterministic 与 local_bge 各 30 条向量可共存；
- deterministic：Recall@5/MRR/nDCG@5/Answerability F1 均为 1.000；
- local_bge：Recall@5/MRR/nDCG@5/Answerability F1 均为 1.000；
- 本地模型：`BAAI/bge-small-zh-v1.5` 与 `BAAI/bge-reranker-base` 在离线模式加载成功；
- 数据性质：上述指标来自 60 条人工标注合成样本，不是生产准确率。

## 4. 产品标准映射

- AC-01：已验证检索返回精确到 chunk 的引用和版本；“最终操作步骤回答”留到 Agent 阶段。
- AC-02：Gate 对本次 10 个无答案/越界负例全部返回不可答；澄清或升级编排留到 Agent 阶段。
- 检索阈值：Recall@5、MRR、nDCG@5 达到首版目标，但样本简单且同源，必须保留限制说明。
- Answerability：本次 F1 达到首版目标；阈值尚未用独立测试集校准。
- 引用：验证了标注来源召回与引用字段映射，尚未评估生成答案逐主张引用正确率和忠实度。

## 5. 剩余风险

- PostgreSQL `simple` 分词对中文正文较弱；当前技术标识和精确短语较多，不能外推到大型中文知识库。
- Gate 阈值与评测集同源，存在过拟合；新增近似干扰和独立测试集后指标可能下降。
- 合成文档只有 10 篇、30 chunk，尚未做大规模索引性能与 p95 延迟测试。
- 本地 Reranker 权重约 1.1 GB，首次下载依赖网络，CPU 推理不代表生产部署成本。
- 目前 API 返回证据而不生成回答，尚未验证忠实度、Prompt Injection 和失败降级编排。
