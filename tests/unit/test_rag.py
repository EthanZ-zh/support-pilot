import math
from uuid import UUID

import pytest

from support_pilot.rag.ingestion import MarkdownChunker
from support_pilot.rag.metrics import (
    aggregate_metrics,
    calculate_binary_metrics,
    calculate_query_metrics,
)
from support_pilot.rag.providers.deterministic import (
    DeterministicEmbeddingProvider,
    DeterministicRerankerProvider,
)
from support_pilot.rag.repository import SearchRow
from support_pilot.rag.retrieval import (
    FusedCandidate,
    HybridRetrievalService,
    reciprocal_rank_fusion,
)


def _row(value: int, *, topic: str = "topic", answer: str = "answer") -> SearchRow:
    return SearchRow(
        chunk_id=UUID(int=value),
        document_id=UUID(int=100 + value),
        title=f"Document {value}",
        source_uri=f"kb://document/{value}",
        product_version="v2",
        authority="official",
        content="evidence",
        heading_path=["Heading"],
        metadata={"topic_code": topic, "answer_key": answer},
        score=1.0,
    )


def test_deterministic_embedding_is_repeatable_and_normalized() -> None:
    provider = DeterministicEmbeddingProvider()

    first = provider.embed_query("Webhook 签名 HMAC-SHA256")
    second = provider.embed_query("Webhook 签名 HMAC-SHA256")

    assert len(first) == 512
    assert first == second
    assert math.sqrt(sum(value * value for value in first)) == pytest.approx(1.0)


def test_deterministic_reranker_prioritizes_exact_technical_identifiers() -> None:
    scores = DeterministicRerankerProvider().score(
        "HTTP 429 返回后 Retry-After 应该怎么处理？",
        [
            "HTTP 429 表示短期限流，客户端应以 Retry-After 为准。",
            "列表接口使用 cursor 分页，默认返回五十条。",
        ],
    )

    assert scores[0] >= DeterministicRerankerProvider.answerability_threshold
    assert scores[0] > scores[1]


def test_markdown_chunker_preserves_heading_path_and_size_boundary() -> None:
    chunks = MarkdownChunker(max_chars=20).chunk(
        "# Authentication\n\nFirst paragraph.\n\nSecond paragraph.\n\n## Errors\n\n401 details."
    )

    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].heading_path == ["Authentication"]
    assert chunks[-1].heading_path == ["Authentication", "Errors"]
    assert all(len(chunk.content) <= 20 for chunk in chunks)


def test_rrf_rewards_a_chunk_found_by_both_retrievers() -> None:
    common = _row(1)
    result = reciprocal_rank_fusion([common, _row(2)], [_row(3), common])

    assert result[0].row.chunk_id == common.chunk_id
    assert result[0].keyword_rank == 1
    assert result[0].vector_rank == 2


def test_answerability_gate_detects_conflicting_official_evidence() -> None:
    candidates = [
        FusedCandidate(row=_row(1, answer="enabled"), rerank_score=0.9),
        FusedCandidate(row=_row(2, answer="disabled"), rerank_score=0.8),
    ]

    assert HybridRetrievalService._has_conflict(candidates)


def test_answerability_gate_rejects_low_relevance() -> None:
    service = object.__new__(HybridRetrievalService)
    service.answerability_threshold = 0.35

    decision = service._answerability([FusedCandidate(row=_row(1), rerank_score=0.1)])

    assert not decision.answerable
    assert decision.reason == "insufficient_relevance"


def test_retrieval_metrics_include_recall_mrr_and_ndcg() -> None:
    result = calculate_query_metrics(["wrong", "right"], {"right"}, k=2)
    aggregate = aggregate_metrics([result])

    assert result.recall_at_k == 1.0
    assert result.reciprocal_rank == 0.5
    assert result.ndcg_at_k == pytest.approx(1 / math.log2(3))
    assert aggregate["mrr"] == 0.5


def test_binary_metrics_report_answerability_errors() -> None:
    result = calculate_binary_metrics(
        [True, True, False, False],
        [True, False, True, False],
    )

    assert result == {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "true_positive": 1,
        "false_positive": 1,
        "false_negative": 1,
        "true_negative": 1,
    }
