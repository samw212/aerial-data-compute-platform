"""Sign in, sign out, who am I, and user administration."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from groma_api.auth import COOKIE_NAME, hash_password, issue_session, verify_password
from groma_api.db import models as m
from groma_api.deps import DB, Admin, Cfg, CurrentUser
from groma_contracts.auth import LoginRequest, Role, SessionInfo, User, UserCreate, UserUpdate

router = APIRouter(prefix="/api", tags=["auth"])


def to_user(u: m.User) -> User:
    return User(
        id=str(u.id),
        email=u.email,
        name=u.name,
        role=Role(u.role),
        org_id=str(u.org_id),
        created_at=u.created_at,
    )


@router.post("/auth/login", response_model=SessionInfo)
def login(body: LoginRequest, response: Response, db: DB, cfg: Cfg) -> SessionInfo:
    user = db.scalar(select(m.User).where(m.User.email == body.email.lower()))
    if user is None or user.disabled or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or password")
    token, expires = issue_session(cfg.jwt_secret, str(user.id), cfg.session_hours)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=cfg.session_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=cfg.secure_cookies,
        path="/",
    )
    return SessionInfo(user=to_user(user), expires_at=expires)


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/auth/me", response_model=User)
def me(user: CurrentUser) -> User:
    return to_user(user)


@router.get("/users", response_model=list[User])
def list_users(_: Admin, db: DB) -> list[User]:
    return [to_user(u) for u in db.scalars(select(m.User).order_by(m.User.email))]


@router.post("/users", response_model=User, status_code=201)
def create_user(body: UserCreate, admin: Admin, db: DB) -> User:
    if db.scalar(select(m.User).where(m.User.email == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "a user with that email exists")
    u = m.User(
        org_id=admin.org_id,
        email=body.email.lower(),
        name=body.name,
        role=body.role.value,
        password_hash=hash_password(body.password),
    )
    db.add(u)
    db.commit()
    return to_user(u)


@router.patch("/users/{user_id}", response_model=User)
def update_user(user_id: uuid.UUID, body: UserUpdate, _: Admin, db: DB) -> User:
    u = db.get(m.User, user_id)
    if u is None:
        raise HTTPException(404, "no such user")
    if body.name is not None:
        u.name = body.name
    if body.role is not None:
        u.role = body.role.value
    if body.password is not None:
        u.password_hash = hash_password(body.password)
    db.commit()
    return to_user(u)
