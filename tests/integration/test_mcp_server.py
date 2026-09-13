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
            assert [tool.name for tool in listed.tools] == [
                "search_support_knowledge"
            ]
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


def test_stdio_server_lists_and_calls_only_knowledge_search(
    db_session: Session,
) -> None:
    _ingest(db_session)
    anyio.run(_happy_path)
