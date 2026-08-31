from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from support_pilot.domain.enums import EscalationReason, TicketCategory, TicketSeverity
from support_pilot.rag.contracts import Citation

AgentIntent = Literal[
    "knowledge",
    "entitlement",
    "quota",
    "incident",
    "ticket_request",
    "high_risk",
    "unknown",
]
AgentOutcome = Literal[
    "answered",
    "needs_clarification",
    "needs_confirmation",
    "escalated",
    "refused",
    "cancelled",
]
ConfirmationAction = Literal["confirm_ticket", "cancel_ticket"]
ConversationStatus = Literal[
    "active",
    "awaiting_clarification",
    "awaiting_confirmation",
    "completed",
    "cancelled",
]


class StrictAgentContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentContext(StrictAgentContract):
    feature_code: str | None = Field(default=None, max_length=100, pattern=r"^[a-z0-9_]+$")
    metric_code: str | None = Field(default=None, max_length=100, pattern=r"^[a-z0-9_]+$")
    component_code: str | None = Field(default=None, max_length=100, pattern=r"^[a-z0-9_]+$")
    region: str | None = Field(default=None, max_length=50)
    occurred_at: datetime | None = None
    product_version: str | None = Field(default=None, max_length=50)
    plan_code: str | None = Field(default=None, max_length=50, pattern=r"^[a-z0-9_]+$")

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("occurred_at must include a timezone offset")
        return value


class AgentRequest(StrictAgentContract):
    session_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID | None = None
    message: str = Field(min_length=2, max_length=2_000)
    context: AgentContext = Field(default_factory=AgentContext)
    confirmation: ConfirmationAction | None = None


class AgentDecision(StrictAgentContract):
    intent: AgentIntent
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=200)


class TraceEvent(StrictAgentContract):
    sequence: int = Field(ge=1)
    node: str
    status: Literal["succeeded", "degraded", "denied"]
    detail: str


class ModelUsage(StrictAgentContract):
    model_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    provider_reported: bool = False
    estimated_cost_cny: float = Field(default=0.0, ge=0.0)
    pricing_basis: str | None = None


class TicketDraft(StrictAgentContract):
    summary: str
    description: str
    category: TicketCategory = TicketCategory.OTHER
    severity: TicketSeverity = TicketSeverity.MEDIUM
    escalation_reason: EscalationReason = EscalationReason.USER_REQUESTED
    requires_confirmation: Literal[True] = True


class AgentResponse(StrictAgentContract):
    request_id: UUID
    session_id: UUID
    trace_id: str
    outcome: AgentOutcome
    intent: AgentIntent
    risk_level: Literal["R1", "R2", "R3"]
    message: str
    response_mode: Literal["extractive", "deterministic", "none"]
    citations: list[Citation] = Field(default_factory=list)
    tool_result: dict[str, Any] | None = None
    ticket_draft: TicketDraft | None = None
    required_fields: list[str] = Field(default_factory=list)
    escalation_reason: str | None = None
    conversation_status: ConversationStatus
    model_usage: ModelUsage
    trace: list[TraceEvent]
