from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from support_pilot.rag.contracts import (
    AnswerabilityDecision,
    Citation,
    KnowledgeSearchInput,
    KnowledgeSearchResponse,
    RetrievalHit,
)
from support_pilot.rag.providers.base import EmbeddingProvider, RerankerProvider
from support_pilot.rag.repository import KnowledgeRepository, SearchRow


@dataclass
class FusedCandidate:
    row: SearchRow
    keyword_rank: int | None = None
    vector_rank: int | None = None
    rrf_score: float = 0.0
    rerank_score: float = 0.0


def reciprocal_rank_fusion(
    keyword_rows: list[SearchRow],
    vector_rows: list[SearchRow],
    *,
    rank_constant: int = 60,
) -> list[FusedCandidate]:
    candidates: dict[UUID, FusedCandidate] = {}
    for rank, row in enumerate(keyword_rows, start=1):
        candidate = candidates.setdefault(row.chunk_id, FusedCandidate(row=row))
        candidate.keyword_rank = rank
        candidate.rrf_score += 1.0 / (rank_constant + rank)
    for rank, row in enumerate(vector_rows, start=1):
        candidate = candidates.setdefault(row.chunk_id, FusedCandidate(row=row))
        candidate.vector_rank = rank
        candidate.rrf_score += 1.0 / (rank_constant + rank)
    return sorted(
        candidates.values(),
        key=lambda candidate: (-candidate.rrf_score, str(candidate.row.chunk_id)),
    )


class HybridRetrievalService:
    def __init__(
        self,
        session: Session,
        *,
        embedding_provider: EmbeddingProvider,
        reranker_provider: RerankerProvider,
        answerability_threshold: float | None = None,
    ) -> None:
        self.repository = KnowledgeRepository(session)
        self.embedding_provider = embedding_provider
        self.reranker_provider = reranker_provider
        self.answerability_threshold = (
            reranker_provider.answerability_threshold
            if answerability_threshold is None
            else answerability_threshold
        )

    def search(self, request: KnowledgeSearchInput) -> KnowledgeSearchResponse:
        keyword_rows = self.repository.keyword_search(
            query=request.query,
            filters=request.filters,
            limit=request.candidate_k,
        )
        query_embedding = self.embedding_provider.embed_query(request.query)
        vector_rows = self.repository.vector_search(
            embedding=query_embedding,
            embedding_provider=self.embedding_provider.provider_name,
            embedding_model=self.embedding_provider.model_name,
            filters=request.filters,
            limit=request.candidate_k,
        )
        fused = reciprocal_rank_fusion(keyword_rows, vector_rows)
        rerank_pool = fused[: request.candidate_k]
        rerank_scores = self.reranker_provider.score(
            request.query,
            [self._rerank_text(candidate.row) for candidate in rerank_pool],
        )
        for candidate, score in zip(rerank_pool, rerank_scores, strict=True):
            candidate.rerank_score = score
        reranked = sorted(
            rerank_pool,
            key=lambda candidate: (
                -candidate.rerank_score,
                -candidate.rrf_score,
                str(candidate.row.chunk_id),
            ),
        )[: request.top_k]
        decision = self._answerability(reranked)
        return KnowledgeSearchResponse(
            query=request.query,
            embedding_provider=self.embedding_provider.provider_name,
            embedding_model=self.embedding_provider.model_name,
            reranker_provider=self.reranker_provider.provider_name,
            reranker_model=self.reranker_provider.model_name,
            filters_applied=request.filters,
            decision=decision,
            hits=[self._to_hit(candidate) for candidate in reranked],
        )

    def _answerability(self, candidates: list[FusedCandidate]) -> AnswerabilityDecision:
        if not candidates:
            return AnswerabilityDecision(
                answerable=False,
                reason="no_evidence",
                evidence_count=0,
                top_score=0.0,
                has_conflict=False,
            )
        top_score = candidates[0].rerank_score
        relevant = [
            candidate
            for candidate in candidates
            if candidate.rerank_score >= self.answerability_threshold
        ]
        has_conflict = self._has_conflict(relevant)
        if has_conflict:
            reason = "conflicting_evidence"
        elif top_score < self.answerability_threshold:
            reason = "insufficient_relevance"
        else:
            reason = "sufficient_evidence"
        return AnswerabilityDecision(
            answerable=reason == "sufficient_evidence",
            reason=reason,
            evidence_count=len(relevant),
            top_score=top_score,
            has_conflict=has_conflict,
        )

    @staticmethod
    def _has_conflict(candidates: list[FusedCandidate]) -> bool:
        answers_by_topic: dict[str, set[str]] = {}
        for candidate in candidates:
            if candidate.row.authority != "official":
                continue
            topic = candidate.row.metadata.get("topic_code")
            answer = candidate.row.metadata.get("answer_key")
            if isinstance(topic, str) and isinstance(answer, str):
                answers_by_topic.setdefault(topic, set()).add(answer)
        return any(len(answers) > 1 for answers in answers_by_topic.values())

    @staticmethod
    def _rerank_text(row: SearchRow) -> str:
        headings = " > ".join(row.heading_path)
        return f"{row.title}\n{headings}\n{row.content}"

    @staticmethod
    def _to_hit(candidate: FusedCandidate) -> RetrievalHit:
        row = candidate.row
        excerpt = row.content if len(row.content) <= 300 else f"{row.content[:297]}..."
        return RetrievalHit(
            citation=Citation(
                chunk_id=row.chunk_id,
                document_title=row.title,
                source_uri=row.source_uri,
                heading_path=row.heading_path,
                product_version=row.product_version,
                excerpt=excerpt,
            ),
            content=row.content,
            metadata=row.metadata,
            keyword_rank=candidate.keyword_rank,
            vector_rank=candidate.vector_rank,
            rrf_score=candidate.rrf_score,
            rerank_score=candidate.rerank_score,
        )
