"""FastAPI dependencies: database session, current user, role checks."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from groma_api.auth import COOKIE_NAME, read_session
from groma_api.db import SessionLocal
from groma_api.db import models as m
from groma_api.settings import Settings, get_settings
from groma_contracts.auth import Role


def get_db() -> Iterator[Session]:
    db = SessionLocal()()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]
Cfg = Annotated[Settings, Depends(get_settings)]


def current_user(request: Request, db: DB, cfg: Cfg) -> m.User:
    token = request.cookies.get(COOKIE_NAME)
    uid = read_session(cfg.jwt_secret, token, cfg.session_hours) if token else None
    user = db.get(m.User, uid) if uid else None
    if user is None or user.disabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
    return user


CurrentUser = Annotated[m.User, Depends(current_user)]


def require(role: Role):  # type: ignore[no-untyped-def]
    def check(user: CurrentUser) -> m.User:
        if not Role(user.role).satisfies(role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires the {role.value} role")
        return user

    return check


Surveyor = Annotated[m.User, Depends(require(Role.SURVEYOR))]
Admin = Annotated[m.User, Depends(require(Role.ADMIN))]
