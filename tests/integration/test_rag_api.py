from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from support_pilot.infrastructure.models import KnowledgeChunkEmbedding, KnowledgeDocument
from support_pilot.rag.contracts import KnowledgeSearchInput, RetrievalFilters
from support_pilot.rag.ingestion import ingest_manifest
from support_pilot.rag.providers.deterministic import (
    DeterministicEmbeddingProvider,
    DeterministicRerankerProvider,
)
from support_pilot.rag.retrieval import HybridRetrievalService

MANIFEST_PATH = Path("data/knowledge/manifest.json").resolve()


class AlternativeDeterministicEmbeddingProvider(DeterministicEmbeddingProvider):
    provider_name = "alternative"
    model_name = "hash-lexical-test-v1"


def _ingest(session: Session) -> None:
    ingest_manifest(
        session,
        manifest_path=MANIFEST_PATH,
        embedding_provider=DeterministicEmbeddingProvider(),
    )


def test_ingestion_is_repeatable_and_preserves_multiple_provider_embeddings(
    db_session: Session,
) -> None:
    _ingest(db_session)
    ingest_manifest(
        db_session,
        manifest_path=MANIFEST_PATH,
        embedding_provider=AlternativeDeterministicEmbeddingProvider(),
    )
    first_document_count = db_session.scalar(select(func.count()).select_from(KnowledgeDocument))
    first_embedding_count = db_session.scalar(
        select(func.count()).select_from(KnowledgeChunkEmbedding)
    )

    _ingest(db_session)

    assert first_document_count == 10
    assert db_session.scalar(select(func.count()).select_from(KnowledgeDocument)) == 10
    assert first_embedding_count == 60
    assert db_session.scalar(select(func.count()).select_from(KnowledgeChunkEmbedding)) == 60


def test_hybrid_search_returns_traceable_citation_and_applies_filters(
    db_session: Session,
) -> None:
    _ingest(db_session)
    service = HybridRetrievalService(
        db_session,
        embedding_provider=DeterministicEmbeddingProvider(),
        reranker_provider=DeterministicRerankerProvider(),
    )

    response = service.search(
        KnowledgeSearchInput(
            query="Webhook 签名为什么必须使用原始 request body？",
            filters=RetrievalFilters(product_version="v2"),
        )
    )
    filtered = service.search(
        KnowledgeSearchInput(
            query="bulk_export 批量导出",
            filters=RetrievalFilters(product_version="v2", plan_code="starter"),
        )
    )

    assert response.decision.answerable
    assert response.hits[0].citation.source_uri == "kb://exampleapi/guides/webhook-signatures"
    assert response.hits[0].citation.excerpt
    assert all(
        hit.citation.source_uri != "kb://exampleapi/features/bulk-export" for hit in filtered.hits
    )


def test_knowledge_search_api_returns_provider_and_evidence(
    client: TestClient,
    db_session: Session,
) -> None:
    _ingest(db_session)

    response = client.post(
        "/api/v1/knowledge/search",
        json={
            "query": "HTTP 429 响应里的 Retry-After 应该如何处理？",
            "filters": {"product_version": "v2"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding_provider"] == "deterministic"
    assert payload["hits"][0]["citation"]["source_uri"] == ("kb://exampleapi/reference/rate-limits")
