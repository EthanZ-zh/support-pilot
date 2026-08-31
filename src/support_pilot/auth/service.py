from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import SecretStr
from sqlalchemy.orm import Session

from support_pilot.auth.contracts import TokenResponse
from support_pilot.config import Settings, get_settings
from support_pilot.domain.enums import UserStatus
from support_pilot.domain.errors import AuthenticationError, DomainError
from support_pilot.infrastructure.models import AuditEvent, UserAccount
from support_pilot.infrastructure.repositories import SupportRepository

ALGORITHM = "HS256"
PASSWORD_HASH = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$MtzpBsirEtF1rPaNlWyDaA$"
    "RSQrj2WRF9eCu6/kcx2N74yMiu1W2v1xGUeRRPYj6b8"
)


class AuthenticationConfigurationError(DomainError):
    """Raised when JWT signing is not configured."""

    status_code = 503
    code = "authentication_unavailable"


def authenticate_user(session: Session, *, email: str, password: str) -> UserAccount:
    normalized_email = email.strip().casefold()
    user = SupportRepository(session).get_user_by_email(normalized_email)
    candidate_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    valid_password = PASSWORD_HASH.verify(password, candidate_hash)
    if user is None or not valid_password or user.status != UserStatus.ACTIVE.value:
        record_auth_event(
            session,
            actor_id=f"email_hash:{sha256(normalized_email.encode()).hexdigest()[:16]}",
            outcome="denied",
            reason_code="invalid_credentials",
        )
        raise AuthenticationError("invalid email or password")
    record_auth_event(
        session,
        actor_id=str(user.id),
        outcome="success",
        reason_code="password_verified",
        tenant_id=user.tenant_id,
    )
    return user


def issue_access_token(
    user: UserAccount,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> TokenResponse:
    resolved = settings or get_settings()
    secret = _require_secret(resolved.jwt_secret)
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=resolved.jwt_access_token_minutes)
    payload = {
        "sub": str(user.id),
        "tid": str(user.tenant_id) if user.tenant_id is not None else None,
        "role": user.role,
        "iss": resolved.jwt_issuer,
        "aud": resolved.jwt_audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
        "jti": uuid4().hex,
    }
    return TokenResponse(
        access_token=jwt.encode(payload, secret, algorithm=ALGORITHM),
        expires_in=resolved.jwt_access_token_minutes * 60,
    )


def authenticate_token(
    session: Session,
    token: str,
    *,
    settings: Settings | None = None,
) -> UserAccount:
    resolved = settings or get_settings()
    secret = _require_secret(resolved.jwt_secret)
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            audience=resolved.jwt_audience,
            issuer=resolved.jwt_issuer,
            options={"require": ["sub", "role", "iss", "aud", "iat", "nbf", "exp", "jti"]},
        )
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise AuthenticationError("invalid or expired bearer token") from None
    user = SupportRepository(session).get_user(user_id)
    expected_tenant = str(user.tenant_id) if user is not None and user.tenant_id else None
    if (
        user is None
        or user.status != UserStatus.ACTIVE.value
        or payload.get("role") != user.role
        or payload.get("tid") != expected_tenant
    ):
        raise AuthenticationError("token identity is no longer active")
    return user


def _require_secret(secret: SecretStr | None) -> str:
    value = secret.get_secret_value() if secret is not None else ""
    if len(value) < 32:
        raise AuthenticationConfigurationError(
            "SUPPORT_PILOT_JWT_SECRET must contain at least 32 characters"
        )
    return value


def record_auth_event(
    session: Session,
    *,
    actor_id: str,
    outcome: str,
    reason_code: str,
    tenant_id: UUID | None = None,
) -> None:
    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_type="user" if outcome == "success" else "system",
            actor_id=actor_id,
            action="auth.authenticate",
            resource_type="session",
            resource_id="access_token",
            outcome=outcome,
            reason_code=reason_code,
            metadata_redacted={},
            trace_id=uuid4().hex,
        )
    )
    session.commit()
