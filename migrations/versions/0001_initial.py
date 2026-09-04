"""Initial schema. Build spec 5, plus users and job logs.

Revision ID: 0001_initial
Revises: None
"""

from __future__ import annotations

from alembic import op

from groma_api.db.base import Base
from groma_api.db import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    # The models are the schema. Emitting them from metadata keeps one source of
    # truth for the first revision; later revisions are hand-written diffs.
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
