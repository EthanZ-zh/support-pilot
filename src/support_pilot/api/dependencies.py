from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from support_pilot.auth.service import authenticate_token, record_auth_event
from support_pilot.config import get_settings
from support_pilot.domain.enums import UserStatus
from support_pilot.domain.errors import AuthenticationError
from support_pilot.infrastructure.database import get_db
from support_pilot.infrastructure.models import UserAccount
from support_pilot.infrastructure.repositories import SupportRepository

SessionDep = Annotated[Session, Depends(get_db)]
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> UserAccount:
    if credentials is not None:
        if credentials.scheme.casefold() != "bearer":
            record_auth_event(
                session,
                actor_id="anonymous",
                outcome="denied",
                reason_code="invalid_authorization_scheme",
            )
            raise AuthenticationError("Authorization scheme must be Bearer")
        try:
            return authenticate_token(session, credentials.credentials)
        except AuthenticationError:
            record_auth_event(
                session,
                actor_id="anonymous",
                outcome="denied",
                reason_code="invalid_bearer_token",
            )
            raise
    if not get_settings().allow_legacy_user_header:
        record_auth_event(
            session,
            actor_id="anonymous",
            outcome="denied",
            reason_code="bearer_token_missing",
        )
        raise AuthenticationError("Bearer token is required")
    if x_user_id is None:
        record_auth_event(
            session,
            actor_id="anonymous",
            outcome="denied",
            reason_code="authentication_missing",
        )
        raise AuthenticationError("Bearer token is required")
    try:
        user_id = UUID(x_user_id)
    except ValueError as error:
        raise AuthenticationError("X-User-Id must be a valid UUID") from error
    user = SupportRepository(session).get_user(user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise AuthenticationError("active user not found")
    return user


CurrentUserDep = Annotated[UserAccount, Depends(get_current_user)]
