# Minimal MCP Knowledge Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one local `stdio` MCP Server that exposes SupportPilot's existing deterministic knowledge retrieval as the read-only `search_support_knowledge` tool.

**Architecture:** Add a single MCP adapter module beside the existing FastAPI entry point. The tool opens a short-lived SQLAlchemy Session, delegates retrieval to `HybridRetrievalService`, and returns a deliberately small Pydantic result; SDK client tests launch the real module as a subprocess and verify the MCP handshake, discovery, invocation, validation, and sanitized failure behavior.

**Tech Stack:** Python 3.11+, official Python MCP SDK 2.x (`mcp>=2.2,<3`), Pydantic, SQLAlchemy, PostgreSQL/pgvector, pytest, AnyIO.

**Spec:** `docs/superpowers/specs/2026-09-11-minimal-mcp-knowledge-search-design.md`

## Global Constraints

- Expose exactly one tool named `search_support_knowledge` over local `stdio` only.
- Reuse `get_session_factory`, `get_provider_bundle`, and `HybridRetrievalService`; do not duplicate retrieval logic.
- Local verification must set `SUPPORT_PILOT_RETRIEVAL_PROVIDER=deterministic` and require no model API key.
- The tool is read-only and must not create tickets, change permissions, call an external model, or expose a network port.
- stdout is reserved for MCP protocol messages; diagnostic logging goes to stderr.
- Database failures must not reveal database URLs, passwords, environment variables, or tracebacks to the MCP caller.
- Do not modify `README.md`, `AGENTS.md`, `docs/career/`, `docs/learning/`, Compose, FastAPI routes, or database migrations.

## File Map

- Modify `pyproject.toml`: add the one required runtime dependency, `mcp>=2.2,<3`.
- Modify `uv.lock`: lock the MCP SDK and its transitive dependencies.
- Create `src/support_pilot/mcp_server.py`: result contracts, one tool, and the `stdio` entry point.
- Create `tests/integration/test_mcp_server.py`: subprocess-level MCP protocol and failure tests.

---

### Task 1: Happy-path MCP protocol adapter

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/support_pilot/mcp_server.py`
- Create: `tests/integration/test_mcp_server.py`

**Interfaces:**
- Consumes: `get_session_factory() -> sessionmaker[Session]`, `get_provider_bundle() -> tuple[EmbeddingProvider, RerankerProvider]`, and `HybridRetrievalService.search(KnowledgeSearchInput) -> KnowledgeSearchResponse`.
- Produces: `mcp: MCPServer`, `search_support_knowledge(query: SearchQuery, product_version: ProductVersion | None = None) -> McpKnowledgeSearchResult`, and `main() -> None`.

- [ ] **Step 1: Add the MCP SDK dependency**

Run:

```powershell
uv add "mcp>=2.2,<3"
```

Expected: `pyproject.toml` contains exactly one new direct dependency and `uv.lock` resolves successfully.

- [ ] **Step 2: Write the failing stdio happy-path test**

Create `tests/integration/test_mcp_server.py` with a real SDK client subprocess:

```python
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy.orm import Session

from support_pilot.rag.ingestion import ingest_manifest
from support_pilot.rag.providers.deterministic import DeterministicEmbeddingProvider

PROJECT_ROOT = Path(__file__).parents[2]
MANIFEST_PATH = PROJECT_ROOT / "data" / "knowledge" / "manifest.json"


def _ingest(session: Session) -> None:
    ingest_manifest(
        session,
        manifest_path=MANIFEST_PATH,
        embedding_provider=DeterministicEmbeddingProvider(),
    )


async def _happy_path() -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "support_pilot.mcp_server"],
        cwd=str(PROJECT_ROOT),
        env=os.environ
        | {
            "SUPPORT_PILOT_RETRIEVAL_PROVIDER": "deterministic",
            "PYTHONUNBUFFERED": "1",
        },
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            assert [tool.name for tool in listed.tools] == ["search_support_knowledge"]
            result = await session.call_tool(
                "search_support_knowledge",
                {
                    "query": "HTTP 429 响应里的 Retry-After 应该如何处理？",
                    "product_version": "v2",
                },
            )

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["answerable"] is True
    assert result.structured_content["hits"][0]["source_uri"] == (
        "kb://exampleapi/reference/rate-limits"
    )


def test_stdio_server_lists_and_calls_only_knowledge_search(db_session: Session) -> None:
    _ingest(db_session)
    anyio.run(_happy_path)
```

- [ ] **Step 3: Run the test to verify the missing server fails**

Run:

```powershell
uv run pytest tests/integration/test_mcp_server.py::test_stdio_server_lists_and_calls_only_knowledge_search -q
```

Expected: FAIL because `support_pilot.mcp_server` does not exist or the subprocess closes before initialization.

- [ ] **Step 4: Implement the minimal MCP adapter**

Create `src/support_pilot/mcp_server.py`:

```python
import logging
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.exc import SQLAlchemyError

from support_pilot.infrastructure.database import get_session_factory
from support_pilot.rag.contracts import KnowledgeSearchInput, RetrievalFilters
from support_pilot.rag.providers.factory import get_provider_bundle
from support_pilot.rag.retrieval import HybridRetrievalService

logger = logging.getLogger(__name__)
mcp = MCPServer("support-pilot")

SearchQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]
ProductVersion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
]


class McpContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class McpKnowledgeHit(McpContract):
    title: str
    source_uri: str
    heading_path: list[str]
    excerpt: str
    rrf_score: float
    rerank_score: float


class McpKnowledgeSearchResult(McpContract):
    embedding_provider: str
    embedding_model: str
    reranker_provider: str
    reranker_model: str
    answerable: bool
    reason: str
    evidence_count: int
    hits: list[McpKnowledgeHit]


@mcp.tool()
def search_support_knowledge(
    query: SearchQuery,
    product_version: ProductVersion | None = None,
) -> McpKnowledgeSearchResult:
    """Search SupportPilot knowledge and return answerability with traceable citations."""
    try:
        embedding_provider, reranker_provider = get_provider_bundle()
        with get_session_factory()() as session:
            response = HybridRetrievalService(
                session,
                embedding_provider=embedding_provider,
                reranker_provider=reranker_provider,
            ).search(
                KnowledgeSearchInput(
                    query=query,
                    filters=RetrievalFilters(product_version=product_version),
                    top_k=5,
                )
            )
    except SQLAlchemyError:
        logger.exception("MCP knowledge search database failure")
        raise ToolError("knowledge search is temporarily unavailable") from None

    return McpKnowledgeSearchResult(
        embedding_provider=response.embedding_provider,
        embedding_model=response.embedding_model,
        reranker_provider=response.reranker_provider,
        reranker_model=response.reranker_model,
        answerable=response.decision.answerable,
        reason=response.decision.reason,
        evidence_count=response.decision.evidence_count,
        hits=[
            McpKnowledgeHit(
                title=hit.citation.document_title,
                source_uri=hit.citation.source_uri,
                heading_path=hit.citation.heading_path,
                excerpt=hit.citation.excerpt,
                rrf_score=hit.rrf_score,
                rerank_score=hit.rerank_score,
            )
            for hit in response.hits[:5]
        ],
    )


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the happy-path test**

Run:

```powershell
uv run pytest tests/integration/test_mcp_server.py::test_stdio_server_lists_and_calls_only_knowledge_search -q
```

Expected: PASS; the real subprocess completes initialize, tools/list, and tools/call.

- [ ] **Step 6: Commit the happy path**

```powershell
git add pyproject.toml uv.lock src/support_pilot/mcp_server.py tests/integration/test_mcp_server.py
git commit -m "feat: expose knowledge search over MCP stdio"
```

### Task 2: Input validation and sanitized database failure

**Files:**
- Modify: `tests/integration/test_mcp_server.py`
- Modify only if the tests reveal a gap: `src/support_pilot/mcp_server.py`

**Interfaces:**
- Consumes: the Task 1 `search_support_knowledge` MCP tool and its Pydantic-generated input schema.
- Produces: protocol evidence that invalid input does not enter retrieval and database errors are sanitized.

- [ ] **Step 1: Add a reusable stdio call helper**

Add to `tests/integration/test_mcp_server.py`:

```python
async def _call_tool(arguments: dict[str, object], env: dict[str, str] | None = None):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "support_pilot.mcp_server"],
        cwd=str(PROJECT_ROOT),
        env=os.environ
        | {
            "SUPPORT_PILOT_RETRIEVAL_PROVIDER": "deterministic",
            "PYTHONUNBUFFERED": "1",
        }
        | (env or {}),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await session.call_tool("search_support_knowledge", arguments)
```

Refactor `_happy_path` to use this helper after its tools/list assertion only where doing so does not hide the explicit protocol sequence.

- [ ] **Step 2: Write failing validation and database-error tests**

```python
def test_stdio_server_rejects_blank_query() -> None:
    result = anyio.run(_call_tool, {"query": "  "})
    assert result.is_error


def test_stdio_server_sanitizes_database_failure() -> None:
    secret = "do-not-leak"
    result = anyio.run(
        _call_tool,
        {"query": "HTTP 429 如何处理？"},
        {
            "SUPPORT_PILOT_DATABASE_URL": (
                f"postgresql+psycopg://support_pilot:{secret}"
                "@127.0.0.1:1/support_pilot_test?connect_timeout=1"
            )
        },
    )
    rendered = " ".join(block.text for block in result.content if hasattr(block, "text"))
    assert result.is_error
    assert "temporarily unavailable" in rendered
    assert secret not in rendered
    assert "postgresql" not in rendered
```

- [ ] **Step 3: Run both tests and inspect the actual failure**

Run:

```powershell
uv run pytest tests/integration/test_mcp_server.py -q
```

Expected before any correction: either PASS with the Task 1 implementation or a focused failure showing an SDK result-shape/error-mapping mismatch. Do not change production code unless the observed failure proves the design is not met.

- [ ] **Step 4: Apply only the evidence-driven correction, if required**

Allowed correction scope:

- adjust the SDK result parsing in the test to the actual MCP 2.2 response type; or
- adjust `ToolError` construction so the caller sees only `knowledge search is temporarily unavailable`.

Do not add a custom exception hierarchy, retry loop, middleware, or logging framework.

- [ ] **Step 5: Re-run the MCP integration tests**

Run:

```powershell
uv run pytest tests/integration/test_mcp_server.py -q
```

Expected: all MCP integration tests PASS.

- [ ] **Step 6: Commit failure-boundary coverage**

```powershell
git add src/support_pilot/mcp_server.py tests/integration/test_mcp_server.py
git commit -m "test: cover MCP validation and database failure"
```

### Task 3: WSL2 protocol smoke test and final quality gate

**Files:**
- No source files expected.
- Modify the implementation or tests only if a verification failure is caused by this change.

**Interfaces:**
- Consumes: the completed `support_pilot.mcp_server` module and running isolated test PostgreSQL service.
- Produces: reproducible Linux/WSL2 protocol evidence and a clean final diff.

- [ ] **Step 1: Prepare the isolated test database**

Run:

```powershell
docker compose up -d --wait postgres-test
$env:SUPPORT_PILOT_TEST_DATABASE_URL = "postgresql+psycopg://support_pilot:support_pilot@127.0.0.1:54330/support_pilot_test"
uv run alembic upgrade head
```

Expected: `postgres-test` is healthy and migrations reach head. Never point tests at the development or production database.

- [ ] **Step 2: Synchronize the existing Ubuntu experiment environment**

Run from WSL2 Ubuntu:

```bash
cd /mnt/d/WorkBuddyData/codex/home/worktrees/646b/support-pilot
/opt/supportpilot-lab-venv/bin/pip install -e .
```

Expected: `mcp>=2.2,<3` installs into the existing experiment virtual environment without modifying repository files.

- [ ] **Step 3: Run a real WSL2 stdio client smoke test**

Run a temporary Python client from Ubuntu that starts:

```bash
/opt/supportpilot-lab-venv/bin/python -m support_pilot.mcp_server
```

through `StdioServerParameters`, then executes initialize, tools/list, and tools/call with the HTTP 429 query. The client must print only:

```text
TOOLS=search_support_knowledge
ANSWERABLE=True
SOURCE=kb://exampleapi/reference/rate-limits
```

Expected: exit 0, with no protocol JSON, secret, or traceback printed to stdout.

- [ ] **Step 4: Run focused and regression checks**

```powershell
uv run pytest tests/integration/test_mcp_server.py tests/integration/test_rag_api.py -q
uv run ruff check src/support_pilot/mcp_server.py tests/integration/test_mcp_server.py
uv run mypy
docker compose config --quiet
```

Expected: all commands exit 0. Existing unrelated failures must be reported separately rather than hidden.

- [ ] **Step 5: Inspect the final change set and secret safety**

```powershell
git status --short --branch
git diff --check HEAD~2..HEAD
git diff --stat HEAD~2..HEAD
git diff --name-only HEAD~2..HEAD
git grep -n "do-not-leak\|DASHSCOPE_API_KEY=" HEAD~2..HEAD -- . ':!uv.lock'
```

Expected: only the planned files changed, diff check exits 0, and no real secret or populated API key appears.

- [ ] **Step 6: Produce the learning checkpoint**

Summarize in chat, without adding another document:

- what MCP initialize, tools/list, and tools/call each do;
- why stdout purity matters for `stdio`;
- why the adapter delegates to the existing RAG service;
- how input validation and `ToolError` form the trust boundary;
- what was deliberately omitted and when it would become necessary.

Do not add an MCP resume bullet until every acceptance criterion above has fresh evidence.
