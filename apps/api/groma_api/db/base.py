from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from groma_api.settings import get_settings


class Base(DeclarativeBase):
    pass


def make_session_factory(url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=create_engine(url, pool_pre_ping=True), expire_on_commit=False)


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10)


@lru_cache
def SessionLocal() -> sessionmaker[Session]:  # noqa: N802 - conventional name
    return sessionmaker(bind=get_engine(), expire_on_commit=False)
