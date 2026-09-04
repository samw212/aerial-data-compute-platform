"""The ADCP background worker. Build spec 5 (jobs), 7, 19.

    python -m groma_worker

Pops job ids from the Redis queue and, on start and every minute, sweeps the job
table for queued rows the push may have missed. Runs one job at a time (the
reconstruction stages are heavy; the kernel is quick). Writes progress and console
lines back to Postgres, which is what the API streams to the browser, so a page
reload or a worker restart loses nothing. Heartbeats to Redis for /api/health.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
import traceback
import uuid
from datetime import UTC, datetime
from typing import cast

from redis import Redis
from sqlalchemy import select

from groma_api.db import SessionLocal
from groma_api.db import models as m
from groma_api.queue import QUEUE_KEY
from groma_api.settings import get_settings
from groma_worker.tasks import HANDLERS, JobContext

log = logging.getLogger("groma.worker")
STOP = False


def _stop(*_: object) -> None:
    global STOP
    STOP = True


def run_job(job_id: uuid.UUID) -> None:
    db = SessionLocal()()
    try:
        job = db.get(m.Job, job_id)
        if job is None or job.status not in ("queued",):
            return
        handler = HANDLERS.get(job.kind)
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.message = None
        db.commit()
        ctx = JobContext(db, job, get_settings())
        try:
            if handler is None:
                raise RuntimeError(f"no handler for job kind {job.kind!r}")
            ctx.log(f"start {job.kind} {job.id}")
            handler(ctx)
            db.refresh(job)
            if job.status == "cancelled":
                ctx.log("cancelled")
                return
            job.status = "succeeded"
            job.progress = 1.0
            job.finished_at = datetime.now(UTC)
            ctx.log("done")
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(m.Job, job_id)
            if job is not None:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"[:2000]
                job.finished_at = datetime.now(UTC)
                db.add(m.JobLog(job_id=job.id, line=f"[ERROR] {exc}"))
                db.add(m.JobLog(job_id=job.id, line=traceback.format_exc()[-3000:]))
                db.commit()
            log.exception("job %s failed", job_id)
    finally:
        db.close()


def sweep(redis: Redis) -> None:
    """Re-queue every queued row: a push can be lost, the row cannot."""
    db = SessionLocal()()
    try:
        for job in db.scalars(
            select(m.Job).where(m.Job.status == "queued").order_by(m.Job.created_at)
        ):
            redis.rpush(QUEUE_KEY, str(job.id))
    finally:
        db.close()


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("GROMA_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker up; queue %s", QUEUE_KEY)
    redis.delete(QUEUE_KEY)
    sweep(redis)
    last_sweep = time.time()
    seen: set[str] = set()
    while not STOP:
        redis.set("groma:worker:heartbeat", datetime.now(UTC).isoformat(), ex=90)
        item = cast("tuple[bytes, bytes] | None", redis.blpop([QUEUE_KEY], timeout=5))
        if item is not None:
            job_id = item[1].decode()
            if job_id not in seen:
                seen.add(job_id)
                try:
                    run_job(uuid.UUID(job_id))
                finally:
                    seen.discard(job_id)
        if time.time() - last_sweep > 60:
            sweep(redis)
            last_sweep = time.time()
    log.info("worker stopping")
    return 0


if __name__ == "__main__":
    sys.exit(main())
