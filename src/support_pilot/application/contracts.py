from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from support_pilot.domain.enums import (
    EscalationReason,
    ResponseOutcome,
    TicketCategory,
    TicketSeverity,
)


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BaseSupportInput(StrictContract):
    session_id: UUID = Field(default_factory=uuid4)
    message: str = Field(min_length=1, max_length=2_000)


class EntitlementInput(BaseSupportInput):
    intent: Literal["entitlement"]
    tenant_id: UUID
    feature_code: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")


class QuotaInput(BaseSupportInput):
    intent: Literal["quota"]
    tenant_id: UUID
    metric_code: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")


class IncidentInput(BaseSupportInput):
    intent: Literal["incident"]
    component_code: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    region: str = Field(min_length=1, max_length=50)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value


class TicketInput(BaseSupportInput):
    intent: Literal["ticket_request"]
    tenant_id: UUID
    summary: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=5_000)
    category: TicketCategory
    severity: TicketSeverity
    escalation_reason: EscalationReason
    diagnostic_context: dict[str, Any] = Field(default_factory=dict)


class HighRiskInput(BaseSupportInput):
    intent: Literal["high_risk"]
    tenant_id: UUID | None = None
    requested_action: str = Field(min_length=3, max_length=200)


SupportInput = Annotated[
    EntitlementInput | QuotaInput | IncidentInput | TicketInput | HighRiskInput,
    Field(discriminator="intent"),
]


class SupportResponse(StrictContract):
    request_id: UUID
    trace_id: str
    outcome: ResponseOutcome
    data: dict[str, Any]
