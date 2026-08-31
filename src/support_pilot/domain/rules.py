import json
from collections.abc import Mapping
from hashlib import sha256
from typing import Any
from uuid import UUID

from support_pilot.domain.enums import Intent, RiskLevel, TicketStatus, UserRole
from support_pilot.domain.errors import InvalidTransitionError

INTERNAL_ROLES = {UserRole.SUPPORT_AGENT, UserRole.KNOWLEDGE_ADMIN}

TICKET_TRANSITIONS: Mapping[TicketStatus, frozenset[TicketStatus]] = {
    TicketStatus.OPEN: frozenset({TicketStatus.TRIAGED}),
    TicketStatus.TRIAGED: frozenset({TicketStatus.IN_PROGRESS}),
    TicketStatus.IN_PROGRESS: frozenset({TicketStatus.WAITING_CUSTOMER, TicketStatus.RESOLVED}),
    TicketStatus.WAITING_CUSTOMER: frozenset({TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED}),
    TicketStatus.RESOLVED: frozenset({TicketStatus.CLOSED, TicketStatus.IN_PROGRESS}),
    TicketStatus.CLOSED: frozenset(),
}


def can_access_tenant(
    *, role: UserRole, actor_tenant_id: UUID | None, target_tenant_id: UUID
) -> bool:
    if role in INTERNAL_ROLES:
        return True
    return actor_tenant_id == target_tenant_id


def risk_for_intent(intent: Intent) -> RiskLevel:
    if intent is Intent.TICKET_REQUEST:
        return RiskLevel.R2
    if intent is Intent.HIGH_RISK:
        return RiskLevel.R3
    return RiskLevel.R1


def ensure_ticket_transition_allowed(current: TicketStatus, target: TicketStatus) -> None:
    if target not in TICKET_TRANSITIONS[current]:
        raise InvalidTransitionError(f"cannot transition ticket from {current} to {target}")


def canonical_request_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()
