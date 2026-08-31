# ADR 0002：pgvector 混合检索与本地 BGE Provider

- 状态：Accepted
- 日期：2026-08-29

## 背景

第三阶段需要验证中文技术支持知识的混合检索、引用和 Answerability Gate，同时保留可重复、无需网络的 CI。知识库必须支持产品版本、套餐和生效时间过滤，模型文件不能写入系统盘。

## 决策

1. PostgreSQL 继续作为唯一业务数据库，通过 `pgvector` 扩展存储 512 维向量；全文索引使用 PostgreSQL `tsvector`。
2. 候选集由关键词与向量双路召回，通过 RRF 融合，再由 Reranker 排序。
3. Provider 接口隔离 Embedding 和 Reranker：
   - `deterministic` 使用特征哈希与词项重合，仅用于 CI、无模型环境和行为回归；
   - `local_bge` 使用 `BAAI/bge-small-zh-v1.5` 与 `BAAI/bge-reranker-base`，用于真实本地评测。
4. 向量存入独立的 `knowledge_chunk_embeddings` 表，以 `(chunk_id, provider, model)` 唯一约束支持同一分块的多套向量共存。
5. 模型缓存默认固定为 `D:/model-cache/support-pilot/huggingface`；下载脚本禁用在本机停滞的 Xet 通道，使用普通 HTTP。
6. Gate 只基于可追溯证据、重排分数和冲突元数据决定是否可回答；它不生成答案，也不把低分证据包装成确定结论。

## 为什么现在需要

- 单纯关键词无法稳定处理中文同义表达，单纯向量检索又可能忽略精确错误码、Header 和版本号。
- RRF 不依赖两路分数处于同一量纲，适合组合不同召回器。
- 分离向量表避免真实模型摄取覆盖 CI 向量，使两种执行模式可在同一数据库验证。

## 替代方案

- 云端 Embedding/Reranker：质量和部署更接近托管服务，但增加费用、密钥、网络和数据出境边界，本阶段不采用。
- Elasticsearch/OpenSearch：全文检索能力更强，但增加一个基础设施组件；当前 30 个合成分块没有业务证据支持该复杂度。
- 只用确定性哈希向量：适合测试，不足以证明真实语义检索能力，因此只作为 CI Provider。

## 代价与限制

- 本地 Reranker 首次下载与 CPU 推理较慢；模型缓存占用 D 盘空间。
- PostgreSQL `simple` 分词对中文正文能力有限，关键词路主要依赖技术标识和精确短语，语义召回由 Embedding 补足。
- 当前评测集是 50 条人工标注的合成问题，不能表述为生产准确率。
- 当前 Gate 阈值来自离线小样本，进入真实数据阶段必须重新校准。

## 验证方式

- 迁移往返与 `alembic check`；
- 摄取幂等、多 Provider 共存、过滤、引用、RRF、Gate 和指标单元/集成测试；
- 分别运行确定性 Provider 与真实本地 BGE 的 50 条离线检索评测；
- 检查模型文件数量、大小和实际 D 盘路径。
