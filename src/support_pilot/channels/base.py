from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID


class ChannelDeliveryError(RuntimeError):
    """External notification delivery failed after the business transaction committed."""


@dataclass(frozen=True, slots=True)
class TicketEvent:
    event_type: Literal["ticket_created", "ticket_updated", "ticket_resolved"]
    ticket_id: UUID
    public_code: str
    tenant_id: UUID
    status: str
    summary: str = ""
    assignee_email: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_payload(self) -> dict[str, str]:
        return {
            "event": self.event_type,
            "ticket_id": str(self.ticket_id),
            "public_code": self.public_code,
            "tenant_id": str(self.tenant_id),
            "status": self.status,
            "summary": self.summary,
            "assignee": self.assignee_email or "",
            "occurred_at": self.occurred_at.isoformat(),
        }


class OutboundChannel(Protocol):
    name: str

    def deliver(self, event: TicketEvent) -> None: ...
