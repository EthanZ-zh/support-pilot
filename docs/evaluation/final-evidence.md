# SupportPilot 最终证据快照

快照时间：2026-09-10（Asia/Shanghai）
数据性质：ExampleAPI 合成业务数据、人工标注合成评测集；不是生产数据。

| 层级 | 样本/检查 | 结果 | 解释边界 |
|---|---:|---:|---|
| RAG calibration | 50 正例 + 10 负例 | deterministic 与 local BGE 四项均 1.000 | 同源小样本，仅用于校准与回归 |
| RAG deterministic holdout | 20 正例 + 10 负例 | Recall@5/MRR/nDCG@5 1.000；Gate F1 0.889 | 冻结后首次运行，FP=0、FN=4 |
| RAG local BGE holdout | 20 正例 + 10 负例 | Recall@5 1.000；MRR 0.975；nDCG@5 0.982；Gate F1 0.974 | 本地 CPU，FP=0、FN=1 |
| Agent deterministic | 80 场景 / 91 步 | 80/80；macro-F1 1.000 | 受控多证据修复后的当前结果 |
| Agent 安全/副作用 | 同上 + 并发集成测试 | 安全升级 Recall 1.000；重复/高风险误执行 0 | 非对抗性生产红队 |
| Qwen3.7 Plus | 7 条冒烟 | 7/7；5 次调用；¥0.0042 估算 | 只证明接入，不证明泛化 |
| 后端工程 | 101 tests | 全通过；coverage 93% | local BGE 实现未进入常规覆盖 |
| 前端工程 | 4 tests + lint/build | 全通过；JS gzip 约 65 kB | jsdom 组件与流解析测试 |
| 浏览器 E2E | 1 条 Chromium 业务闭环 | 登录、SSE/引用、确认工单、认领并推进 `in_progress` 全通过 | deterministic Provider、隔离测试库 |
| 数据库迁移 | upgrade + check | 当前 head，无模型漂移 | 独立测试数据库 |
| 本地演示 | 知识→确认→工单→认领→推进 | answered + 实际采用证据引用；ticket in_progress | deterministic Provider |
| 容器 | 本地 config + GitHub Actions runtime | Linux runner 构建镜像、Compose 启动并通过 API/前端/代理探活 | 本机构建受 Docker Hub 网络阻断；非生产部署 |
| GitHub Actions | backend / frontend / e2e / container | 4/4 success | `main@7007b49` |

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
npx playwright install chromium
npm run test:e2e
```

当前机器结果：`docs/evaluation/results/agent-scenarios-v1-multi-evidence.json`、`docs/evaluation/results/retrieval-holdout-deterministic-v1.json`、`docs/evaluation/results/retrieval-holdout-local-bge-v1.json`。原报告仍保留为历史基线。
