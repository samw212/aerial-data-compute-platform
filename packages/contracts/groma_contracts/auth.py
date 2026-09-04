"""Users and roles. Build spec 7, 19.5.

Structure review and GCP marking require an authenticated surveyor: the audit trail
is worthless if anonymous. Roles are ordered; a role satisfies any requirement at
or below it.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Role(StrEnum):
    VIEWER = "viewer"
    SURVEYOR = "surveyor"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return _RANK[self]

    def satisfies(self, required: "Role") -> bool:
        return self.rank >= required.rank


_RANK = {Role.VIEWER: 0, Role.SURVEYOR: 1, Role.ADMIN: 2}


class User(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: Role = Role.VIEWER
    org_id: str
    created_at: datetime | None = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: EmailStr
    password: str = Field(min_length=1)


class SessionInfo(BaseModel):
    user: User
    expires_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    role: Role = Role.VIEWER
    password: str = Field(min_length=10)


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    password: str | None = Field(default=None, min_length=10)


__all__ = ["LoginRequest", "Role", "SessionInfo", "User", "UserCreate", "UserUpdate"]
