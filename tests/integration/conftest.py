"""Integration tests run against a real PostGIS. Build spec 18.

Set GROMA_TEST_DATABASE_URL (a database that may be dropped and recreated). On
the AutoDL instance that is the local groma_test database; on a workstation a
postgis/postgis container; in CI a service container. Skipped when unset.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

TEST_DB = os.environ.get("GROMA_TEST_DATABASE_URL")
REPO = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.skipif(not TEST_DB, reason="GROMA_TEST_DATABASE_URL not set")


@pytest.fixture(scope="session", autouse=True)
def _env(tmp_path_factory: pytest.TempPathFactory) -> None:
    if not TEST_DB:
        pytest.skip("GROMA_TEST_DATABASE_URL not set")
    os.environ["GROMA_DATABASE_URL"] = TEST_DB
    os.environ["GROMA_JWT_SECRET"] = "test-secret-test-secret-test-secret-0000"
    os.environ["GROMA_ARTEFACT_ROOT"] = str(tmp_path_factory.mktemp("artefacts"))
    os.environ["GROMA_REDIS_URL"] = "redis://127.0.0.1:1/0"  # unreachable on purpose
    from groma_api.settings import get_settings

    get_settings.cache_clear()


@pytest.fixture(scope="session")
def seeded(_env: None) -> dict[str, str]:
    """A fresh schema with site_alpha loaded, once per session."""
    from groma_api.db.base import SessionLocal, get_engine
    from groma_api.seed import reset_schema, seed

    get_engine.cache_clear()
    SessionLocal.cache_clear()
    db = SessionLocal()()
    try:
        reset_schema(db)
        return seed(
            db,
            REPO / "fixtures" / "sites" / "site_alpha.json",
            "admin@test.local",
            "test-password-123",
        )
    finally:
        db.close()


@pytest.fixture(scope="session")
def app(seeded: dict[str, str]):  # type: ignore[no-untyped-def]
    from groma_api.main import app as _app

    return _app


@pytest.fixture()
def anon(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin(app, seeded: dict[str, str]) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app) as c:
        r = c.post(
            "/api/auth/login", json={"email": "admin@test.local", "password": "test-password-123"}
        )
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture()
def viewer(app, seeded: dict[str, str], admin: TestClient) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    admin.post(
        "/api/users",
        json={
            "email": "viewer@test.local",
            "name": "V",
            "role": "viewer",
            "password": "viewer-password-1",
        },
    )
    with TestClient(app) as c:
        r = c.post(
            "/api/auth/login", json={"email": "viewer@test.local", "password": "viewer-password-1"}
        )
        assert r.status_code == 200
        yield c


@pytest.fixture()
def db_session(seeded):  # type: ignore[no-untyped-def]
    from groma_api.db.base import SessionLocal

    db = SessionLocal()()
    try:
        yield db
    finally:
        db.close()


_ = (create_engine, text, sessionmaker)
