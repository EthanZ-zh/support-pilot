from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from support_pilot.infrastructure.models import (
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
    KnowledgeDocument,
)
from support_pilot.rag.contracts import RetrievalFilters


@dataclass(frozen=True)
class SearchRow:
    chunk_id: UUID
    document_id: UUID
    title: str
    source_uri: str
    product_version: str | None
    authority: str
    content: str
    heading_path: list[str]
    metadata: dict[str, Any]
    score: float


class KnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def keyword_search(
        self,
        *,
        query: str,
        filters: RetrievalFilters,
        limit: int,
    ) -> list[SearchRow]:
        ts_query = func.plainto_tsquery("simple", query)
        matches_fts = KnowledgeChunk.search_vector.op("@@")(ts_query)
        exact_phrase = func.strpos(func.lower(KnowledgeChunk.search_text), query.lower()) > 0
        score = (
            func.ts_rank_cd(KnowledgeChunk.search_vector, ts_query)
            + case((exact_phrase, 0.5), else_=0.0)
        ).label("retrieval_score")
        statement = (
            select(KnowledgeChunk, KnowledgeDocument, score)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(or_(matches_fts, exact_phrase), *self._filter_conditions(filters))
            .order_by(score.desc(), KnowledgeChunk.id)
            .limit(limit)
        )
        return [
            self._to_row(chunk, document, value)
            for chunk, document, value in self.session.execute(statement)
        ]

    def vector_search(
        self,
        *,
        embedding: list[float],
        embedding_provider: str,
        embedding_model: str,
        filters: RetrievalFilters,
        limit: int,
    ) -> list[SearchRow]:
        distance = KnowledgeChunkEmbedding.embedding.cosine_distance(embedding)
        score = (1.0 - distance).label("retrieval_score")
        statement = (
            select(KnowledgeChunk, KnowledgeDocument, score)
            .join(
                KnowledgeChunkEmbedding,
                KnowledgeChunkEmbedding.chunk_id == KnowledgeChunk.id,
            )
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeChunkEmbedding.provider == embedding_provider,
                KnowledgeChunkEmbedding.model == embedding_model,
                *self._filter_conditions(filters),
            )
            .order_by(distance, KnowledgeChunk.id)
            .limit(limit)
        )
        return [
            self._to_row(chunk, document, value)
            for chunk, document, value in self.session.execute(statement)
        ]

    @staticmethod
    def _filter_conditions(filters: RetrievalFilters) -> list[Any]:
        conditions: list[Any] = [KnowledgeDocument.status == "published"]
        conditions.extend(
            [
                or_(
                    KnowledgeDocument.effective_from.is_(None),
                    KnowledgeDocument.effective_from <= filters.at,
                ),
                or_(
                    KnowledgeDocument.effective_to.is_(None),
                    KnowledgeDocument.effective_to > filters.at,
                ),
            ]
        )
        if filters.product_version is not None:
            conditions.append(
                or_(
                    KnowledgeDocument.product_version.is_(None),
                    KnowledgeDocument.product_version == filters.product_version,
                )
            )
        if filters.plan_code is not None:
            conditions.append(
                or_(
                    KnowledgeDocument.applicable_plans == [],
                    KnowledgeDocument.applicable_plans.contains([filters.plan_code]),
                )
            )
        return conditions

    @staticmethod
    def _to_row(
        chunk: KnowledgeChunk,
        document: KnowledgeDocument,
        score: float,
    ) -> SearchRow:
        return SearchRow(
            chunk_id=chunk.id,
            document_id=document.id,
            title=document.title,
            source_uri=document.source_uri,
            product_version=document.product_version,
            authority=document.authority,
            content=chunk.content,
            heading_path=chunk.heading_path,
            metadata=chunk.metadata_json,
            score=float(score),
        )
