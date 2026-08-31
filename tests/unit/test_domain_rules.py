from uuid import UUID

import pytest

from support_pilot.domain.enums import Intent, RiskLevel, TicketStatus, UserRole
from support_pilot.domain.errors import InvalidTransitionError
from support_pilot.domain.rules import (
    can_access_tenant,
    canonical_request_hash,
    ensure_ticket_transition_allowed,
    risk_for_intent,
)
from support_pilot.domain.sanitization import REDACTED, redact_text, redact_value

TENANT_A = UUID("20000000-0000-0000-0000-000000000001")
TENANT_B = UUID("20000000-0000-0000-0000-000000000002")
SYNTHETIC_SECRET = "exa_live_" + ("1" * 10)
SYNTHETIC_BEARER = "Bearer " + ("a" * 16)


def test_tenant_access_is_deterministic() -> None:
    assert can_access_tenant(
        role=UserRole.TENANT_ADMIN,
        actor_tenant_id=TENANT_A,
        target_tenant_id=TENANT_A,
    )
    assert not can_access_tenant(
        role=UserRole.TENANT_ADMIN,
        actor_tenant_id=TENANT_A,
        target_tenant_id=TENANT_B,
    )
    assert can_access_tenant(
        role=UserRole.SUPPORT_AGENT,
        actor_tenant_id=None,
        target_tenant_id=TENANT_B,
    )


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        (Intent.ENTITLEMENT, RiskLevel.R1),
        (Intent.QUOTA, RiskLevel.R1),
        (Intent.INCIDENT, RiskLevel.R1),
        (Intent.TICKET_REQUEST, RiskLevel.R2),
        (Intent.HIGH_RISK, RiskLevel.R3),
    ],
)
def test_risk_level_cannot_be_selected_by_caller(intent: Intent, expected: RiskLevel) -> None:
    assert risk_for_intent(intent) is expected


def test_ticket_state_machine_rejects_skipping_required_states() -> None:
    ensure_ticket_transition_allowed(TicketStatus.OPEN, TicketStatus.TRIAGED)
    with pytest.raises(InvalidTransitionError):
        ensure_ticket_transition_allowed(TicketStatus.OPEN, TicketStatus.CLOSED)


def test_canonical_hash_ignores_mapping_order() -> None:
    assert canonical_request_hash({"a": 1, "b": 2}) == canonical_request_hash({"b": 2, "a": 1})


def test_secrets_are_redacted_recursively() -> None:
    assert redact_text(f"key={SYNTHETIC_SECRET}") == f"key={REDACTED}"
    assert redact_value(
        {
            "api_key": "anything",
            "nested": {"authorization": SYNTHETIC_BEARER},
            "safe": "request_123",
        }
    ) == {
        "api_key": REDACTED,
        "nested": {"authorization": REDACTED},
        "safe": "request_123",
    }
