from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from support_pilot.domain.enums import (
    EscalationReason,
    TicketCategory,
    TicketSeverity,
    TicketStatus,
)


class StrictTicketContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TicketTransitionResponse(StrictTicketContract):
    id: UUID
    from_status: TicketStatus
    to_status: TicketStatus
    actor_id: UUID
    reason: str
    created_at: datetime


class TicketResponse(StrictTicketContract):
    id: UUID
    public_code: str
    tenant_id: UUID
    status: TicketStatus
    severity: TicketSeverity
    category: TicketCategory
    summary: str
    description: str
    diagnostic_context: dict[str, Any]
    escalation_reason: EscalationReason
    assignee_id: UUID | None
    agent_run_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    transitions: list[TicketTransitionResponse] = Field(default_factory=list)
    replayed: bool = False


class TicketListResponse(StrictTicketContract):
    items: list[TicketResponse]
    total: int


class ClaimTicketRequest(StrictTicketContract):
    expected_version: int = Field(ge=1)


class TransitionTicketRequest(StrictTicketContract):
    to_status: TicketStatus
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class HumanFeedbackRequest(StrictTicketContract):
    agent_run_id: UUID
    disposition: Literal["accepted", "edited", "rejected"]
    resolution_category: TicketCategory
    knowledge_gap: bool
    comment: str | None = Field(default=None, max_length=2_000)


class HumanFeedbackResponse(StrictTicketContract):
    id: UUID
    ticket_id: UUID
    agent_run_id: UUID
    reviewer_id: UUID
    disposition: Literal["accepted", "edited", "rejected"]
    resolution_category: TicketCategory
    knowledge_gap: bool
    comment: str | None
    created_at: datetime
    replayed: bool = False
