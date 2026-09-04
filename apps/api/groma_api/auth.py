"""Passwords and sessions. Build spec 7 (roles), 19.5.

Sessions are a signed, expiring cookie carrying the user id: no session table, so
a restart forgets nothing and a stolen cookie expires. Passwords are argon2id.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE_NAME = "adcp_session"

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret, salt="adcp-session")


def issue_session(secret: str, user_id: str, hours: int) -> tuple[str, datetime]:
    token = _serializer(secret).dumps({"uid": user_id})
    return token, datetime.now(UTC) + timedelta(hours=hours)


def read_session(secret: str, token: str, hours: int) -> str | None:
    """The user id in a valid, unexpired session token, else None."""
    try:
        data = _serializer(secret).loads(token, max_age=hours * 3600)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    return str(uid) if uid else None


__all__ = ["COOKIE_NAME", "hash_password", "issue_session", "read_session", "verify_password"]
