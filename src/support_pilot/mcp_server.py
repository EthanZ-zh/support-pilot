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

SearchQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=500),
]
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
    """Search SupportPilot knowledge and return answerability with citations."""
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
