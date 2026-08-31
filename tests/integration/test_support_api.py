from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from support_pilot.application.contracts import TicketInput
from support_pilot.application.services import SupportService
from support_pilot.infrastructure.models import (
    AuditEvent,
    SupportRequestRecord,
    Ticket,
    UserAccount,
)
from support_pilot.infrastructure.seed import (
    TENANT_ALPHA_ID,
    TENANT_BETA_ID,
    USER_ALPHA_ADMIN_ID,
)

AUTH_HEADERS = {"X-User-Id": str(USER_ALPHA_ADMIN_ID)}
SYNTHETIC_SECRET = "exa_live_" + ("1" * 10)


def test_request_requires_authenticated_user(client: TestClient) -> None:
    response = client.post(
        "/api/v1/support/resolve",
        json={
            "intent": "entitlement",
            "message": "查询权益",
            "tenant_id": str(TENANT_ALPHA_ID),
            "feature_code": "bulk_export",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_entitlement_query_uses_tenant_data_and_redacts_message(
    client: TestClient, db_session: Session
) -> None:
    response = client.post(
        "/api/v1/support/resolve",
        headers=AUTH_HEADERS,
        json={
            "intent": "entitlement",
            "message": f"请检查 {SYNTHETIC_SECRET} 为什么不能批量导出",
            "tenant_id": str(TENANT_ALPHA_ID),
            "feature_code": "bulk_export",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "tenant_id": str(TENANT_ALPHA_ID),
        "plan_code": "starter",
        "feature_code": "bulk_export",
        "enabled": False,
        "source": "plan",
    }
    stored_request = db_session.scalar(select(SupportRequestRecord))
    assert stored_request is not None
    assert stored_request.raw_message == "请检查 [REDACTED] 为什么不能批量导出"
    assert db_session.scalar(select(func.count(AuditEvent.id))) == 1


def test_cross_tenant_query_is_denied_and_audited(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/api/v1/support/resolve",
        headers=AUTH_HEADERS,
        json={
            "intent": "entitlement",
            "message": "查看另一个租户的权益",
            "tenant_id": str(TENANT_BETA_ID),
            "feature_code": "bulk_export",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "tenant_access_denied"
    audit = db_session.scalar(select(AuditEvent))
    assert audit is not None
    assert audit.outcome == "denied"
    assert audit.reason_code == "cross_tenant_access_denied"
    assert audit.tenant_id == TENANT_BETA_ID


def test_quota_is_calculated_by_code(client: TestClient) -> None:
    response = client.post(
        "/api/v1/support/resolve",
        headers=AUTH_HEADERS,
        json={
            "intent": "quota",
            "message": "本月还剩多少调用额度？",
            "tenant_id": str(TENANT_ALPHA_ID),
            "metric_code": "api_requests_monthly",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["remaining"] == 2_500
    assert response.json()["data"]["exceeded"] is False


def test_incident_query_distinguishes_match_from_no_match(client: TestClient) -> None:
    base_payload = {
        "intent": "incident",
        "message": "新加坡区域 API 超时",
        "component_code": "rest_api",
        "region": "ap-southeast-1",
    }
    matched = client.post(
        "/api/v1/support/resolve",
        headers=AUTH_HEADERS,
        json={**base_payload, "occurred_at": "2026-08-01T10:20:00Z"},
    )
    not_matched = client.post(
        "/api/v1/support/resolve",
        headers=AUTH_HEADERS,
        json={**base_payload, "occurred_at": "2026-08-02T10:20:00Z"},
    )

    assert matched.status_code == 200
    assert matched.json()["data"]["match_status"] == "confirmed_incident"
    assert matched.json()["data"]["incidents"][0]["public_code"] == "INC-2026-0801"
    assert not_matched.status_code == 200
    assert not_matched.json()["data"]["match_status"] == "no_matching_incident"
    assert "不代表服务一定正常" in not_matched.json()["data"]["notice"]


def test_ticket_creation_is_idempotent_and_rejects_changed_payload(
    client: TestClient, db_session: Session
) -> None:
    headers = {**AUTH_HEADERS, "Idempotency-Key": "ticket-demo-001"}
    payload = _ticket_payload()

    created = client.post("/api/v1/support/resolve", headers=headers, json=payload)
    replayed = client.post("/api/v1/support/resolve", headers=headers, json=payload)
    conflict = client.post(
        "/api/v1/support/resolve",
        headers=headers,
        json={**payload, "summary": "不同的问题摘要"},
    )

    assert created.status_code == 200
    assert created.json()["data"]["replayed"] is False
    assert replayed.status_code == 200
    assert replayed.json()["data"]["replayed"] is True
    assert replayed.json()["data"]["ticket_id"] == created.json()["data"]["ticket_id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_conflict"
    assert db_session.scalar(select(func.count(Ticket.id))) == 1


def test_ticket_creation_requires_idempotency_key(client: TestClient) -> None:
    response = client.post(
        "/api/v1/support/resolve",
        headers=AUTH_HEADERS,
        json=_ticket_payload(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "request_precondition_failed"


def test_concurrent_ticket_retries_create_one_side_effect(
    session_factory: sessionmaker[Session],
) -> None:
    barrier = Barrier(2)
    request = TicketInput.model_validate(_ticket_payload())

    def create_ticket() -> str:
        with session_factory() as session:
            actor = session.get(UserAccount, USER_ALPHA_ADMIN_ID)
            assert actor is not None
            barrier.wait(timeout=5)
            response = SupportService(session).process(
                request,
                actor=actor,
                idempotency_key="concurrent-ticket-001",
            )
            return str(response.data["ticket_id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        ticket_ids = list(executor.map(lambda _index: create_ticket(), range(2)))

    with session_factory() as session:
        assert len(set(ticket_ids)) == 1
        assert session.scalar(select(func.count(Ticket.id))) == 1


def test_high_risk_action_is_refused_without_ticket(
    client: TestClient, db_session: Session
) -> None:
    response = client.post(
        "/api/v1/support/resolve",
        headers=AUTH_HEADERS,
        json={
            "intent": "high_risk",
            "message": "请立即轮换生产密钥",
            "tenant_id": str(TENANT_ALPHA_ID),
            "requested_action": "rotate_production_api_key",
        },
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "refused"
    assert response.json()["data"]["executed"] is False
    assert db_session.scalar(select(func.count(Ticket.id))) == 0
    audit = db_session.scalar(select(AuditEvent))
    assert audit is not None
    assert audit.action == "high_risk.execute"
    assert audit.outcome == "denied"


def _ticket_payload() -> dict[str, object]:
    return {
        "intent": "ticket_request",
        "message": "请帮我提交工单",
        "tenant_id": str(TENANT_ALPHA_ID),
        "summary": "生产环境 API 持续返回 403",
        "description": "从 10:20 开始持续失败，request_id=req_demo_001。",
        "category": "authentication",
        "severity": "high",
        "escalation_reason": "user_requested",
        "diagnostic_context": {
            "request_id": "req_demo_001",
            "api_key": SYNTHETIC_SECRET,
        },
    }
