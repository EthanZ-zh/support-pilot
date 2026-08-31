from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.auth.service import authenticate_token, issue_access_token
from support_pilot.config import Settings
from support_pilot.domain.errors import AuthenticationError
from support_pilot.infrastructure.models import AuditEvent, UserAccount

DEMO_PASSWORD = "SupportPilotDemo!2026"


def test_login_issues_short_lived_bearer_and_me_returns_identity(
    client: TestClient,
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "beta.developer@example.com",
            "password": DEMO_PASSWORD,
        },
    )

    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"
    assert login.json()["expires_in"] == 1800

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["email"] == "beta.developer@example.com"
    assert me.json()["role"] == "customer_developer"
    assert "password_hash" not in me.json()


def test_login_rejects_wrong_password_without_issuing_token(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "beta.developer@example.com",
            "password": "not-the-demo-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "auth.authenticate", AuditEvent.outcome == "denied")
        .order_by(AuditEvent.created_at.desc())
    )
    assert audit is not None
    assert audit.reason_code == "invalid_credentials"
    assert "beta.developer" not in audit.actor_id


def test_tampered_bearer_token_is_rejected(client: TestClient) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "beta.developer@example.com",
            "password": DEMO_PASSWORD,
        },
    )
    token = login.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token[:-1]}x"},
    )

    assert response.status_code == 401


def test_expired_token_and_role_drift_are_rejected(db_session: Session) -> None:
    user = db_session.scalar(
        select(UserAccount).where(UserAccount.email == "beta.developer@example.com")
    )
    assert user is not None
    settings = Settings(
        _env_file=None,
        jwt_secret=SecretStr("unit-test-jwt-secret-with-at-least-32-characters"),
    )
    expired = issue_access_token(
        user,
        settings=settings,
        now=datetime(2020, 1, 1, tzinfo=UTC),
    )
    try:
        authenticate_token(db_session, expired.access_token, settings=settings)
    except AuthenticationError:
        pass
    else:
        raise AssertionError("expired token must be rejected")

    current = issue_access_token(user, settings=settings)
    user.role = "tenant_admin"
    db_session.commit()
    try:
        authenticate_token(db_session, current.access_token, settings=settings)
    except AuthenticationError:
        pass
    else:
        raise AssertionError("token with stale role claim must be rejected")


def test_legacy_identity_header_is_disabled_by_default(
    client: TestClient,
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "support_pilot.api.dependencies.get_settings",
        lambda: Settings(
            _env_file=None,
            jwt_secret=SecretStr("unit-test-jwt-secret-with-at-least-32-characters"),
            allow_legacy_user_header=False,
        ),
    )
    user = db_session.scalar(select(UserAccount).where(UserAccount.role == "customer_developer"))
    assert user is not None

    response = client.get(
        "/api/v1/tickets",
        headers={"X-User-Id": str(user.id)},
    )

    assert response.status_code == 401
    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.reason_code == "bearer_token_missing")
        .order_by(AuditEvent.created_at.desc())
    )
    assert audit is not None
