# SupportPilot 指标口径与证据索引

## 项目定位

个人项目｜企业 SaaS 技术支持与智能工单 Agent｜合成数据与公开模型，非生产环境交付。

技术栈：Python、FastAPI、LangGraph、PostgreSQL、pgvector、SQLAlchemy、Alembic、React、TypeScript、Vite、JWT/RBAC、OpenTelemetry、Docker Compose、GitHub Actions。

## 项目要点

**SupportPilot｜企业 SaaS 技术支持与智能工单 Agent（个人项目）**

- 设计并实现 Provider 中立的 LangGraph 支持工作流，将意图/风险识别、混合 RAG、确定性业务工具、Answerability Gate、显式工单确认与人工接管串成可持久化闭环；用同文档/同主题/同版本的受控多证据门控解决跨 chunk 问题，80 条人工标注合成场景（91 个请求步骤）全部通过，重复副作用与高风险误执行均为 0。
- 基于 PostgreSQL/pgvector 实现关键词与向量双路召回、RRF、BGE Reranker、元数据过滤和 chunk 级引用；拆分 60 条 calibration 与 30 条冻结后 holdout，本地 BGE 在 holdout 上的 Recall@5 1.000、MRR 0.975、nDCG@5 0.982、Answerability F1 0.974，无答案误放行为 0。
- 构建 JWT/RBAC、多租户隔离、工单状态机、事务/幂等/乐观锁与审计，使用 React + SSE 展示真实节点 Trace、引用和人工处理；101 个后端测试覆盖率 93%，4 个前端单元测试及 1 条 Chromium 业务 E2E 通过，CI 还验证 Compose 构建、启动和前端反向代理探活。

## 指标证据索引

| 指标口径 | 证据 | 限制 |
|---|---|---|
| 80/80 Agent 场景 | `docs/evaluation/results/agent-scenarios-v1-multi-evidence.json` | 确定性 Provider、合成场景 |
| Intent macro-F1 1.000 | 同上，91 个带标签步骤 | 不代表 Qwen 泛化质量 |
| local BGE holdout Recall@5 1.000 / Gate F1 0.974 | `docs/evaluation/results/retrieval-holdout-local-bge-v1.json` | 30 条独立 ID 合成样本，仍非生产数据 |
| calibration 四项 1.000 | `docs/evaluation/stage-3-rag-evaluation.md` | 60 条同源合成样本，仅作校准/回归 |
| Qwen 7/7 冒烟 | `docs/evaluation/stage-4-qwen-smoke-evaluation.md` | 仅 7 条、调用 5 次 |
| 0 重复副作用/高风险误执行 | Agent 机器报告 + PostgreSQL 并发测试 | 非生产流量 |
| 101 tests / 93% | 2026-09-10 全量 pytest 记录 | local BGE 文件未计入常规覆盖 |
| 4 frontend tests | Vitest + Testing Library | jsdom 单元/组件层 |
| 1 browser E2E | Playwright Chromium：客户提问到人工处理 | deterministic Provider、单浏览器、隔离测试库 |
| Compose runtime | `main@7007b49` container job | CI runner 短时启动与探活，不代表生产稳定性 |

## 演示顺序（5–7 分钟）

1. 用客户账号提交 429 问题，指出实时 Trace、引用 URI 和 Gate 后的回答。
2. 提交"无法解决，请创建工单"，强调只有草稿；点击确认后才发生低风险写入。
3. 切换支持账号，认领工单并推进状态，解释 Idempotency-Key 与 version 的区别。
4. 提交人工反馈，展示反馈只进入质量数据，不自动污染知识库。
5. 打开 80 场景报告，展示 401/403 如何在不降低阈值的前提下用受控多证据通过 Gate，并保留两条引用。

## 表述边界

- 不声称"服务真实企业客户""线上准确率 98.75%""生产节省多少人力"；
- 不把 Qwen macro-F1 写成 1.0——1.0 属于确定性 80 场景，Qwen 只有 7 条冒烟；
- 不声称"已经生产部署"——GitHub Actions 已验证镜像构建、整套 Compose 启动与短时探活，但未验证生产配置、容量、可用性或长期稳定性；
- 不声称"防住所有 Prompt Injection"——当前是规则预检、证据扫描和工具隔离的 MVP 防线。
