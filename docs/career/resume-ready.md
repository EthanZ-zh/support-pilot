# SupportPilot 求职交付说明

## 项目定位

个人项目｜企业 SaaS 技术支持与智能工单 Agent｜合成数据与公开模型，不是实习或生产项目。

技术栈：Python、FastAPI、LangGraph、PostgreSQL、pgvector、SQLAlchemy、Alembic、React、TypeScript、Vite、JWT/RBAC、OpenTelemetry、Docker Compose、GitHub Actions。

## 可直接使用的简历描述

**SupportPilot｜企业 SaaS 技术支持与智能工单 Agent（个人项目）**

- 设计并实现 Provider 中立的 LangGraph 支持工作流，将意图/风险识别、混合 RAG、确定性业务工具、Answerability Gate、显式工单确认与人工接管串成可持久化闭环；在 80 条人工标注合成场景（91 个请求步骤）上通过 79 条，Intent macro-F1 1.000，安全升级 Recall 1.000，重复副作用与高风险误执行均为 0。
- 基于 PostgreSQL/pgvector 实现关键词与向量双路召回、RRF、BGE Reranker、元数据过滤和 chunk 级引用；在 50 个可答 + 10 个无答案合成样本上，确定性与本地 BGE 基线的 Recall@5、MRR、nDCG@5、Answerability F1 均为 1.000，并保留同源小样本/阈值过拟合限制。
- 构建 JWT/RBAC、多租户隔离、工单状态机、事务/幂等/乐观锁与审计，使用 React + SSE 展示真实节点 Trace、引用和人工处理；66 个后端测试覆盖率 93%，4 个前端测试及 lint/type/build 通过，并提供 Alembic 往返、OTLP 埋点、CI、Compose 与可复现演示脚本。

若版面紧张，可把第三条末尾缩为：“66 个后端测试覆盖率 93%，前端 lint/test/build 与 Alembic 往返通过。”不要写“容器部署验证通过”，直到镜像实际构建成功。

## 指标证据索引

| 简历口径 | 证据 | 限制 |
|---|---|---|
| 79/80 Agent 场景 | `docs/evaluation/results/agent-scenarios-v1.json` | 确定性 Provider、合成场景 |
| Intent macro-F1 1.000 | 同上，91 个带标签步骤 | 不代表 Qwen 泛化质量 |
| RAG 四项 1.000 | `docs/evaluation/stage-3-rag-evaluation.md` | 60 条同源合成样本 |
| Qwen 7/7 冒烟 | `docs/evaluation/stage-4-qwen-smoke-evaluation.md` | 仅 7 条、调用 5 次 |
| 0 重复副作用/高风险误执行 | Agent 机器报告 + PostgreSQL 并发测试 | 非生产流量 |
| 66 tests / 93% | 2026-08-31 全量 pytest 记录 | local BGE 文件未计入常规覆盖 |
| 4 frontend tests | Vitest + Testing Library | jsdom，不是真实浏览器 E2E |

## 面试演示顺序（5–7 分钟）

1. 用客户账号提交 429 问题，指出实时 Trace、引用 URI 和 Gate 后的回答。
2. 提交“无法解决，请创建工单”，强调只有草稿；点击确认后才发生低风险写入。
3. 切换支持账号，认领工单并推进状态，解释 Idempotency-Key 与 version 的区别。
4. 提交人工反馈，展示反馈只进入质量数据，不自动污染知识库。
5. 打开 80 场景报告，主动讲 401/403 多证据问题为什么选择安全升级而没有调低阈值。

## 不能使用的表述

- “服务真实企业客户”“线上准确率 98.75%”“生产节省多少人力”；
- “Qwen macro-F1 1.0”——1.0 属于确定性 80 场景，Qwen 只有 7 条冒烟；
- “已经生产部署”“容器已验证”——当前 Docker Hub 网络阻断了镜像拉取；
- “防住所有 Prompt Injection”——当前是规则预检、证据扫描和工具隔离的 MVP 防线。
