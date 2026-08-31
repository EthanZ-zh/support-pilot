# SupportPilot 最终证据快照

快照时间：2026-08-31（Asia/Shanghai）  
数据性质：ExampleAPI 合成业务数据、人工标注合成评测集；不是生产数据。

| 层级 | 样本/检查 | 结果 | 解释边界 |
|---|---:|---:|---|
| RAG deterministic | 50 正例 + 10 负例 | Recall@5/MRR/nDCG@5/F1 = 1.000 | 同源小样本 |
| RAG local BGE | 50 正例 + 10 负例 | Recall@5/MRR/nDCG@5/F1 = 1.000 | 本地 CPU，同源小样本 |
| Agent deterministic | 80 场景 / 91 步 | 79/80；macro-F1 1.000 | 1 条多证据失败 |
| Agent 安全/副作用 | 同上 + 并发集成测试 | 安全升级 Recall 1.000；重复/高风险误执行 0 | 非对抗性生产红队 |
| Qwen3.7 Plus | 7 条冒烟 | 7/7；5 次调用；¥0.0042 估算 | 只证明接入，不证明泛化 |
| 后端工程 | 66 tests | 全通过；coverage 93% | local BGE 实现未进入常规覆盖 |
| 前端工程 | 4 tests + lint/build | 全通过；JS gzip 64.70 kB | jsdom，非浏览器 E2E |
| 数据库迁移 | 0006 ↔ 0005 | downgrade/upgrade/check 通过 | 独立测试数据库 |
| 本地演示 | 知识→确认→工单→认领→推进 | answered + 3 citations；ticket in_progress | deterministic Provider |
| 容器 | config + 2 次 build | config 通过；build 被 Docker Hub TCP 超时阻断 | 不声明镜像已验证 |

## 复现命令

```powershell
docker compose up -d postgres postgres-test
uv run alembic upgrade head
uv run python scripts/seed.py
uv run python scripts/ingest_knowledge.py --provider deterministic
uv run ruff check .
uv run mypy
uv run pytest --cov=support_pilot --cov-report=term-missing

Set-Location frontend
npm ci
npm run lint
npm run test
npm run build
```

机器结果：`docs/evaluation/results/agent-scenarios-v1.json`、`docs/evaluation/results/retrieval-deterministic-v2.json`。
