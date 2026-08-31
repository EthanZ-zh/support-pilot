from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from support_pilot.infrastructure.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended', 'closed')", name="valid_status"),
        CheckConstraint(
            "data_origin IN ('synthetic', 'human_labeled', 'public')",
            name="valid_data_origin",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id"), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="synthetic")

    plan: Mapped[Plan] = relationship(lazy="joined")


class UserAccount(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('customer_developer', 'tenant_admin', 'support_agent', 'knowledge_admin')",
            name="valid_role",
        ),
        CheckConstraint("status IN ('active', 'disabled')", name="valid_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class Entitlement(Base, TimestampMixin):
    __tablename__ = "entitlements"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "feature_code", "effective_from", name="uq_entitlement_window"
        ),
        CheckConstraint("source IN ('plan', 'override', 'trial')", name="valid_source"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    feature_code: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuotaSnapshot(Base, TimestampMixin):
    __tablename__ = "quota_snapshots"
    __table_args__ = (
        CheckConstraint('"limit" >= 0', name="non_negative_limit"),
        CheckConstraint("used >= 0", name="non_negative_used"),
        CheckConstraint("period_end > period_start", name="valid_period"),
        Index(
            "ix_quota_snapshot_lookup",
            "tenant_id",
            "metric_code",
            "measured_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    metric_code: Mapped[str] = mapped_column(String(100), nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ServiceComponent(Base, TimestampMixin):
    __tablename__ = "service_components"
    __table_args__ = (
        UniqueConstraint("code", "region", name="uq_service_component_code_region"),
        CheckConstraint(
            "status IN ('operational', 'degraded', 'partial_outage', 'major_outage', "
            "'maintenance')",
            name="valid_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


incident_components = Table(
    "incident_components",
    Base.metadata,
    Column("incident_id", ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "component_id",
        ForeignKey("service_components.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Incident(Base, TimestampMixin):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("severity IN ('sev1', 'sev2', 'sev3', 'sev4')", name="valid_severity"),
        CheckConstraint(
            "status IN ('investigating', 'identified', 'monitoring', 'resolved')",
            name="valid_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    public_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    regions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_message: Mapped[str] = mapped_column(Text, nullable=False)
    internal_notes: Mapped[str | None] = mapped_column(Text)

    components: Mapped[list[ServiceComponent]] = relationship(secondary=incident_components)


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('guide', 'api_reference', 'faq', 'known_issue', 'runbook', "
            "'release_note', 'ticket_resolution')",
            name="valid_doc_type",
        ),
        CheckConstraint(
            "authority IN ('official', 'synthetic_ticket', 'public_reference')",
            name="valid_authority",
        ),
        CheckConstraint(
            "data_origin IN ('synthetic', 'human_labeled', 'public')",
            name="valid_data_origin",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'superseded', 'archived')",
            name="valid_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    product_version: Mapped[str | None] = mapped_column(String(50))
    applicable_plans: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authority: Mapped[str] = mapped_column(String(30), nullable=False)
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    license: Mapped[str | None] = mapped_column(String(100))
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.ordinal",
    )


class KnowledgeChunk(Base, TimestampMixin):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_knowledge_chunk_ordinal"),
        Index(
            "ix_knowledge_chunks_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    heading_path: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, search_text)", persisted=True),
    )
    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")
    embeddings: Mapped[list["KnowledgeChunkEmbedding"]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
    )


class KnowledgeChunkEmbedding(Base, TimestampMixin):
    __tablename__ = "knowledge_chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "provider", "model", name="uq_chunk_embedding_model"),
        Index(
            "ix_knowledge_chunk_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(512), nullable=False)

    chunk: Mapped[KnowledgeChunk] = relationship(back_populates="embeddings")


class SupportRequestRecord(Base):
    __tablename__ = "support_requests"
    __table_args__ = (
        CheckConstraint(
            "intent IN ('entitlement', 'quota', 'incident', 'ticket_request', 'high_risk')",
            name="valid_intent",
        ),
        CheckConstraint("risk_level IN ('R1', 'R2', 'R3')", name="valid_risk_level"),
        CheckConstraint(
            "status IN ('received', 'running', 'answered', 'escalated', 'failed', 'refused')",
            name="valid_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    raw_message: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(30), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'answered', 'needs_clarification', "
            "'needs_confirmation', 'escalated', 'refused', 'cancelled', 'failed')",
            name="valid_status",
        ),
        CheckConstraint(
            "intent IS NULL OR intent IN ('knowledge', 'entitlement', 'quota', 'incident', "
            "'ticket_request', 'high_risk', 'unknown')",
            name="valid_intent",
        ),
        CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('R1', 'R2', 'R3')",
            name="valid_risk_level",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    raw_message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(30))
    risk_level: Mapped[str | None] = mapped_column(String(2))
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    trace_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class AgentConversation(Base, TimestampMixin):
    __tablename__ = "agent_conversations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'awaiting_clarification', 'awaiting_confirmation', "
            "'completed', 'cancelled')",
            name="valid_status",
        ),
        CheckConstraint(
            "pending_intent IS NULL OR pending_intent IN ('knowledge', 'entitlement', "
            "'quota', 'incident', 'ticket_request', 'high_risk', 'unknown')",
            name="valid_pending_intent",
        ),
        CheckConstraint("version >= 1", name="positive_version"),
    )

    session_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    pending_intent: Mapped[str | None] = mapped_column(String(30))
    pending_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ticket_draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ticket_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confirmation_key_hash: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Ticket(Base, TimestampMixin):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'triaged', 'in_progress', 'waiting_customer', "
            "'resolved', 'closed')",
            name="valid_status",
        ),
        CheckConstraint("severity IN ('low', 'medium', 'high', 'urgent')", name="valid_severity"),
        CheckConstraint(
            "category IN ('authentication', 'entitlement', 'quota', 'incident', "
            "'integration', 'other')",
            name="valid_category",
        ),
        CheckConstraint(
            "escalation_reason IN ('user_requested', 'low_answerability', 'high_risk', "
            "'tool_failure', 'security_or_privacy', 'unknown')",
            name="valid_escalation_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    public_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    source_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("support_requests.id"), unique=True, nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    diagnostic_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    escalation_reason: Mapped[str] = mapped_column(String(40), nullable=False)
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TicketTransition(Base):
    __tablename__ = "ticket_transitions"
    __table_args__ = (
        CheckConstraint(
            "from_status IN ('open', 'triaged', 'in_progress', 'waiting_customer', "
            "'resolved', 'closed')",
            name="valid_from_status",
        ),
        CheckConstraint(
            "to_status IN ('open', 'triaged', 'in_progress', 'waiting_customer', "
            "'resolved', 'closed')",
            name="valid_to_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str] = mapped_column(String(30), nullable=False)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class HumanFeedback(Base):
    __tablename__ = "human_feedback"
    __table_args__ = (
        CheckConstraint(
            "disposition IN ('accepted', 'edited', 'rejected')",
            name="valid_disposition",
        ),
        CheckConstraint(
            "resolution_category IN ('authentication', 'entitlement', 'quota', "
            "'incident', 'integration', 'other')",
            name="valid_resolution_category",
        ),
        UniqueConstraint(
            "ticket_id",
            "agent_run_id",
            "reviewer_id",
            name="uq_human_feedback_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    resolution_category: Mapped[str] = mapped_column(String(30), nullable=False)
    knowledge_gap: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint("status IN ('processing', 'succeeded', 'failed')", name="valid_status"),
    )

    scope: Mapped[str] = mapped_column(String(150), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'agent', 'system')", name="valid_actor_type"),
        CheckConstraint("outcome IN ('success', 'failure', 'denied')", name="valid_outcome"),
        Index("ix_audit_event_trace_created", "trace_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_redacted: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
