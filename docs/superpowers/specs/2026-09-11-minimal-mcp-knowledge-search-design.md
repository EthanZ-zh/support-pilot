# 最小 MCP 知识检索实验设计

## 目标

为 AI 应用开发求职学习建立一个可运行、可测试的最小 MCP 闭环：MCP Client 通过本地 `stdio` 启动 SupportPilot MCP Server，发现并调用一个只读知识检索工具，获得 Answerability 判断和可追溯引用。

本实验验证 MCP 协议与现有 RAG 业务能力的适配，不把 MCP 预设为 SupportPilot 的生产依赖。

## 范围

唯一工具：`search_support_knowledge`。

输入：

- `query: str`：必填，去除首尾空白后长度为 2 至 500；
- `product_version: str | None`：可选，透传为现有检索元数据过滤条件。

输出：

- 当前 embedding 与 reranker provider/model；
- `answerable`、`reason`、`evidence_count`；
- 最多 5 条命中，每条仅返回标题、`source_uri`、标题路径、摘录和相关分数。

## 架构与数据流

新增一个独立 MCP 入口模块，不修改 FastAPI 路由：

`MCP Client → stdio → MCP tool → SQLAlchemy Session → HybridRetrievalService → PostgreSQL/pgvector → 结构化结果`

工具直接复用现有 `get_session_factory`、`get_provider_bundle` 和 `HybridRetrievalService`。每次调用创建短生命周期数据库 Session，调用结束后关闭。检索 provider 固定使用项目当前配置；本地验收显式设置为 `deterministic`，不需要模型 API Key。

采用官方 Python MCP SDK 的普通 `mcp` 包，不安装 `cli` extra，不引入第二个 MCP 框架。Server 仅支持 `stdio`，不监听网络端口。

## 错误与安全边界

- 输入 Schema 在 MCP 边界校验，空查询、超长查询和非法版本值不进入业务服务；
- 数据库不可用时返回简短、脱敏的工具错误，不返回数据库 URL、密码或堆栈；
- 工具只读，不创建工单、不修改权限、不调用外部模型；
- stdout 只用于 MCP 协议消息，诊断日志只能写 stderr；
- 不读取或输出 `DASHSCOPE_API_KEY` 等密钥。

## 预计改动

- `pyproject.toml`、`uv.lock`：增加普通 `mcp` SDK 依赖；
- `src/support_pilot/mcp_server.py`：Server 与唯一 Tool；
- `tests/integration/test_mcp_server.py`：协议级成功、参数错误和数据库失败验证。

不修改 `README.md`、`AGENTS.md`、`docs/career/`、`docs/learning/`、Compose、数据库迁移或现有 API。

## 验收标准

1. SDK Client 能通过 `stdio` 完成 initialize、tools/list 和 tools/call；
2. tools/list 只暴露 `search_support_knowledge`，Schema 与约束正确；
3. 已知知识问题返回 answerable 和至少一条 `kb://` 引用；
4. 空查询在协议边界失败；
5. 数据库不可用时调用失败且输出不包含凭据；
6. 相关 pytest、Ruff、Mypy 通过，Git diff 无无关文件和密钥。

## 明确不做

- 不实现 MCP Resource、Prompt、Sampling、认证或 Streamable HTTP；
- 不包装 Agent，不加入会话状态、写工具、缓存、重试框架或遥测扩展；
- 不创建 Docker 服务，不接入 Claude Desktop/Codex 等具体宿主配置；
- 不为未来工具提前设计注册表、工厂或插件体系。
