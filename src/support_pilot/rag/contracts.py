from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictRagContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RetrievalFilters(StrictRagContract):
    product_version: str | None = Field(default=None, max_length=50)
    plan_code: str | None = Field(default=None, max_length=50, pattern=r"^[a-z0-9_]+$")
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeSearchInput(StrictRagContract):
    query: str = Field(min_length=2, max_length=500)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    top_k: int = Field(default=5, ge=1, le=10)
    candidate_k: int = Field(default=20, ge=5, le=100)


class Citation(StrictRagContract):
    chunk_id: UUID
    document_title: str
    source_uri: str
    heading_path: list[str]
    product_version: str | None
    excerpt: str


class RetrievalHit(StrictRagContract):
    citation: Citation
    content: str
    metadata: dict[str, Any]
    keyword_rank: int | None
    vector_rank: int | None
    rrf_score: float
    rerank_score: float


class AnswerabilityDecision(StrictRagContract):
    answerable: bool
    reason: str
    evidence_count: int
    top_score: float
    has_conflict: bool


class KnowledgeSearchResponse(StrictRagContract):
    query: str
    embedding_provider: str
    embedding_model: str
    reranker_provider: str
    reranker_model: str
    filters_applied: RetrievalFilters
    decision: AnswerabilityDecision
    hits: list[RetrievalHit]
