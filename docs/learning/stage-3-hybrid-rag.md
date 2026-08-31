# 第三阶段学习说明：可评测的混合 RAG

## 1. 架构变化

```text
Markdown + manifest
    ↓ heading-aware chunking + checksum + metadata
knowledge_documents / knowledge_chunks
    ├─ PostgreSQL tsvector → keyword candidates
    └─ provider-specific pgvector → vector candidates
                         ↓
                     RRF fusion
                         ↓
                       Rerank
                         ↓
          Answerability Gate + citations
                         ↓
             POST /api/v1/knowledge/search
```

RAG 目前是独立、可评测的检索能力，还没有让 LLM 生成最终回复。下一阶段 Agent 会消费它的结构化结果，但不能绕过 Gate 或伪造引用。

## 2. 一次检索请求的完整链路

1. API 用 `KnowledgeSearchInput` 校验 query、`top_k`、候选数和元数据过滤条件。
2. `KnowledgeRepository` 对已发布且当前生效的文档执行版本、套餐过滤。
3. 关键词路使用生成的 `tsvector`，向量路只读取与当前 Provider/Model 精确匹配的向量。
4. `reciprocal_rank_fusion` 按名次融合候选，不直接相加不可比较的原始分数。
5. Reranker 对 query 与候选正文逐对评分，取前 K 条。
6. Gate 检查最高相关度和同主题官方证据冲突，返回 `sufficient_evidence`、`no_evidence`、`insufficient_relevance` 或 `conflicting_evidence`。
7. 每条命中返回稳定 `chunk_id`、文档标题、`source_uri`、标题路径、版本和摘录，后续回答只能引用这些证据。

## 3. 摄取为什么需要独立向量表

CI 使用确定性 Provider，演示使用真实 BGE。如果把向量直接放在 `knowledge_chunks.embedding`，第二次摄取会覆盖第一次模型结果。独立表用 `(chunk_id, provider, model)` 保证唯一，同一个分块可保留多套向量；正文 checksum 改变时才清理旧分块和全部过期向量。

## 4. 关键取舍

- 用 manifest 显式声明版本、套餐、来源、许可证和数据性质，避免从正文让模型猜元数据。
- 用稳定 UUID5 和 checksum 支持可重复摄取，避免每次运行制造重复分块。
- 当前中文关键词路不引入 Elasticsearch；小规模知识库先验证混合召回的业务价值。
- 确定性 Provider 只证明流程可重复，真实 BGE 结果才用于说明本地语义检索表现。
- Answerability 不是“模型觉得能答”，而是可测试的证据门控；阈值仍需用更真实数据校准。

## 5. 实现中发现的问题

- 最初把 `CrossEncoder.predict()` 返回的概率再次做 sigmoid，无关证据从接近 0 被抬到约 0.5，10 个负例全部误放行。打印原始正负样本分数后移除重复变换。
- 最初只评测 50 个可答问题，检索指标满分却没有暴露 Gate 错误；加入 10 个无答案/越界负例并计算 Precision/Recall/F1 后才发现。
- deterministic 的词项重合分数与 BGE 概率不在同一量纲，因此阈值属于 Provider 契约，不能在 Service 中硬编码一个全局值。
- 单个 `knowledge_chunks.embedding` 会让真实模型覆盖 CI 向量；拆为多 Provider 向量表后才能并存和复现。
- Windows 上 Hugging Face Xet 经代理停滞，改为普通 HTTP 固定文件续传；最终用 SHA-256 校验权重并在离线模式加载。

## 6. 你需要掌握的知识点

- Embedding bi-encoder 召回与 cross-encoder 重排的计算成本和职责差异；
- Recall@K、MRR、nDCG 分别衡量“是否召回”“首个正确结果多靠前”“整体排序质量”；
- RRF 为什么比直接相加 BM25/向量分数更稳健；
- 元数据过滤为什么必须发生在检索阶段，而不是生成后再补救；
- 引用溯源需要保存哪些稳定字段；
- 为什么小样本离线满分不等于生产准确率；
- 多 Provider 数据模型如何避免模型切换破坏可重复性。

## 7. 面试表达

### 30 秒

“我把 RAG 做成了独立可评测能力：PostgreSQL 同时做全文和 pgvector 召回，先按版本、套餐、生效时间过滤，再用 RRF 融合和 cross-encoder 重排。每条结果带稳定引用，Answerability Gate 对低相关或冲突证据拒答。CI 用确定性 Provider，真实本地 BGE 用于离线评测，两套向量可以共存。”

### 3 分钟

沿 manifest 摄取、heading-aware chunk、双路 SQL、RRF、Rerank、Gate、Citation 和 50 条评测集完整讲一遍，再说明为什么当前合成集不能代表生产、中文全文分词的限制，以及下一阶段 Agent 如何消费这个受控检索接口。

### 深入追问

- 为什么向量检索之前要做版本和套餐过滤？
- RRF 的常数 60 对结果有什么影响，如何调参？
- Cross-encoder 为什么不直接对全库运行？
- 文档内容变化后如何防止旧向量继续被召回？
- 如何为 Answerability 阈值制作校准集并权衡误答与升级？
- 两份官方文档冲突时为什么不能简单选择分数更高的一份？
