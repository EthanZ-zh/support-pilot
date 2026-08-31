# SupportPilot

SupportPilot 是面向虚构 B2B API 平台 `ExampleAPI` 的技术支持与智能工单 Agent。本仓库已完成从确定性业务基线、混合 RAG、受控 Agent、安全闭环到 React 控制台的纵向业务链路。

> 所有租户、用户、事故和工单样例均为合成数据，不代表真实企业或生产效果。

## 当前请求链路

`POST /api/v1/auth/login → Argon2id 校验 → JWT → Bearer 身份 → 租户授权 → PostgreSQL 查询/写入 → 审计`

支持的结构化 intent：

- `entitlement`：查询租户功能权益；
- `quota`：查询最新额度快照并由代码计算剩余额度；
- `incident`：按组件、区域和时间查询匹配事故；
- `ticket_request`：通过 `Idempotency-Key` 幂等创建工单；
- `high_risk`：拒绝退款、权限修改、密钥操作和运维命令等高风险动作。

JWT/RBAC、人工接管 API、状态机、幂等反馈、领域级多轮恢复和 LangGraph 节点级 SSE 进度已经实现。持久化的是会话和每次运行的最终状态与 Trace；跨进程节点级 checkpoint 仍是后续增强项。

知识检索链路：

`POST /api/v1/knowledge/search → metadata filters → keyword/vector recall → RRF → rerank → Answerability Gate → citations`

Agent 链路：

`POST /api/v1/agent/resolve/stream → load conversation → safety preflight → DecisionProvider/resume → risk gate → RAG/read tool/draft/confirm/refusal → progress SSE → AgentConversation + AgentRun + trace`

当前 Agent 使用确定性 Provider 做 CI 和流程回归，并已实现和真实验证百炼 Qwen3.7 Plus 意图分类适配器；知识答案仍是有引用的抽取式结果，不伪装成模型生成结果。7 条真实 Provider 冒烟结果记录在阶段评测报告中，不能视为生产准确率。

## 本地运行

要求：Python 3.11+、[uv](https://docs.astral.sh/uv/) 和正在运行的 Docker Desktop。

```powershell
uv sync --group dev
docker compose up -d postgres
uv run alembic upgrade head
uv run python scripts/seed.py
uv run python scripts/ingest_knowledge.py --provider deterministic
uv run uvicorn support_pilot.main:app --reload
```

首次运行前生成本地 JWT 密钥并保存到 Windows 用户环境（新终端生效）：

```powershell
$jwtBytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($jwtBytes)
$jwtSecret = [Convert]::ToHexString($jwtBytes)
[Environment]::SetEnvironmentVariable('SUPPORT_PILOT_JWT_SECRET', $jwtSecret, 'User')
```

检查服务：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
```

使用合成演示账号登录，再查询租户 Alpha 的 `bulk_export` entitlement：

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/login `
  -ContentType 'application/json' `
  -Body (@{
    email = 'alpha.admin@example.com'
    password = 'SupportPilotDemo!2026'
  } | ConvertTo-Json)

$body = @{
  intent = 'entitlement'
  message = '为什么不能使用批量导出？'
  tenant_id = '20000000-0000-0000-0000-000000000001'
  feature_code = 'bulk_export'
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/support/resolve `
  -Headers @{ Authorization = "Bearer $($login.access_token)" } `
  -ContentType 'application/json' `
  -Body $body
```

API 文档位于 `http://127.0.0.1:8000/docs`。

启动 React 控制台（另开终端，npm 缓存保留在 D 盘）：

```powershell
Set-Location frontend
$env:npm_config_cache = 'D:\model-cache\support-pilot\npm'
npm ci
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。客户演示账号为 `alpha.admin@example.com`，支持人员账号为 `support.agent@example.com`，两者使用仓库合成数据约定的演示密码 `SupportPilotDemo!2026`。该密码不能用于任何真实环境。

运行可复现业务演示（后端已启动且完成知识摄取）：

```powershell
.\scripts\demo.ps1
```

脚本会验证“带引用知识回答 → 客户确认工单 → 支持人员认领 → 推进处理中”，并输出 ticket code 与 trace id。

Docker Compose 也包含 API 和前端：

```powershell
docker compose build api frontend
docker compose up -d
```

本机 2026-08-31 的两次镜像构建在拉取基础镜像时被 Docker Hub TCP 超时阻断；Compose 配置已验证，但在网络恢复并实际 build/up 前不得把容器运行写成已验证能力。

启用 Qwen 时，在被 Git 忽略的 `.env` 中把 `SUPPORT_PILOT_AGENT_PROVIDER` 改为 `qwen`。API Key 推荐保存为 Windows 用户级 `DASHSCOPE_API_KEY`；也支持只写在 `.env` 的 `SUPPORT_PILOT_QWEN_API_KEY`。绝不能把真实 Key 写入 `.env.example`，该文件只是可提交的空模板。共享北京 Base URL 可用于开发；正式部署应改为与 Key 同一业务空间的专属域名。未配置 Key 时 Agent API 会返回 503，不会静默回退或泄露密钥。

真实本地 RAG 使用 BGE 模型，默认缓存到 D 盘：

```powershell
$env:UV_CACHE_DIR = 'D:\model-cache\support-pilot\uv'
$env:HF_HOME = 'D:\model-cache\support-pilot\huggingface'
uv sync --group dev --group rag-local
uv run python scripts/download_rag_models.py
uv run python scripts/ingest_knowledge.py --provider local_bge
uv run python scripts/evaluate_retrieval.py --provider local_bge
```

可通过 `SUPPORT_PILOT_MODEL_CACHE_DIR` 覆盖模型目录。真实模型首次下载和 CPU 重排较慢；确定性 Provider 只用于 CI 和流程回归。

## 验证

```powershell
docker compose up -d postgres-test
uv run ruff check .
uv run mypy
uv run pytest
uv run alembic check
Set-Location frontend
npm run lint
npm run test
npm run build
```

集成测试默认连接：

`postgresql+psycopg://support_pilot:support_pilot@localhost:54330/support_pilot_test`

可以通过 `SUPPORT_PILOT_TEST_DATABASE_URL` 覆盖。测试会清空项目表中的数据，因此测试服务使用独立数据库和临时文件系统，不能把该变量指向开发或生产数据库。

## 文档

- [产品定义](./docs/product/product-definition.md)
- [数据字典](./docs/product/data-dictionary.md)
- [验收标准](./docs/product/acceptance-criteria.md)
- [第二阶段验收](./docs/product/stage-2-acceptance.md)
- [第三阶段验收](./docs/product/stage-3-acceptance.md)
- [第四阶段首个增量](./docs/product/stage-4-agent-increment.md)
- [第四阶段验收](./docs/product/stage-4-acceptance.md)
- [第五阶段安全闭环验收](./docs/product/stage-5-acceptance.md)
- [第六阶段全栈体验验收](./docs/product/stage-6-acceptance.md)
- [第七阶段工程质量验收](./docs/product/stage-7-acceptance.md)
- [第八阶段求职交付验收](./docs/product/stage-8-acceptance.md)
- [确定性基线 ADR](./docs/adr/0001-deterministic-modular-monolith.md)
- [混合 RAG ADR](./docs/adr/0002-pgvector-hybrid-retrieval-and-local-bge.md)
- [受控 Agent ADR](./docs/adr/0003-provider-neutral-langgraph-agent.md)
- [LLM Provider 选型决策](./docs/adr/0004-primary-llm-provider.md)
- [可恢复会话与工单幂等 ADR](./docs/adr/0005-recoverable-conversation-and-ticket-confirmation.md)
- [本地 JWT 与人工工单闭环 ADR](./docs/adr/0006-local-jwt-and-human-ticket-workflow.md)
- [SSE、OTLP 与容器交付 ADR](./docs/adr/0007-sse-console-otel-and-container-delivery.md)
- [第二阶段学习说明](./docs/learning/stage-2-deterministic-baseline.md)
- [第三阶段学习说明](./docs/learning/stage-3-hybrid-rag.md)
- [第四阶段学习说明](./docs/learning/stage-4-agent-increment.md)
- [第五阶段学习说明](./docs/learning/stage-5-security-loop.md)
- [第六阶段学习说明](./docs/learning/stage-6-fullstack-console.md)
- [第七阶段学习说明](./docs/learning/stage-7-engineering-quality.md)
- [第三阶段离线评测](./docs/evaluation/stage-3-rag-evaluation.md)
- [第四阶段 Qwen 冒烟评测](./docs/evaluation/stage-4-qwen-smoke-evaluation.md)
- [第四阶段 Agent 80 场景评测](./docs/evaluation/stage-4-agent-evaluation.md)
- [最终证据快照](./docs/evaluation/final-evidence.md)
- [系统架构](./docs/architecture/system-overview.md)
- [项目复盘](./docs/retrospectives/project-retrospective.md)
- [简历描述与证据索引](./docs/career/resume-ready.md)
- [面试讲解与追问](./docs/career/interview-guide.md)
