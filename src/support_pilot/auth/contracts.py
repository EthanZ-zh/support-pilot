from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from support_pilot.domain.enums import UserRole


class StrictAuthContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictAuthContract):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class TokenResponse(StrictAuthContract):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class CurrentUserResponse(StrictAuthContract):
    id: UUID
    tenant_id: UUID | None
    email: EmailStr
    display_name: str
    role: UserRole
