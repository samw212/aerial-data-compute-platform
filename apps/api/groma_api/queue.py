"""Handing a job row to the arq worker over Redis."""

from __future__ import annotations

import uuid

from redis import Redis

from groma_api.settings import get_settings

QUEUE_KEY = "groma:jobs"


def submit(job_id: uuid.UUID) -> None:
    """Push the id; the worker pops it and reads the row. Idempotent: the worker
    also scans for queued rows on start, so a lost push is recovered."""
    r = Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
    r.rpush(QUEUE_KEY, str(job_id))


__all__ = ["QUEUE_KEY", "submit"]
