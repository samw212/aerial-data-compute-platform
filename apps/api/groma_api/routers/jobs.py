"""Jobs and their progress stream. Build spec 7.

Rows live in Postgres so a job survives a worker restart and a page reload. The
worker (arq) picks up queued rows; progress and console lines are written back
here and fanned out over the WebSocket. Until the worker is deployed, the queue
holds and the UI says so.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from groma_api.db import SessionLocal
from groma_api.db import models as m
from groma_api.deps import DB, CurrentUser, Surveyor
from groma_contracts.jobs import Job, JobKind, JobStatus

router = APIRouter(prefix="/api", tags=["jobs"])


class JobOut(Job):
    params: dict[str, Any] | None = None
    created_at: datetime | None = None


class LogLine(BaseModel):
    at: datetime
    line: str


def to_job(j: m.Job) -> JobOut:
    return JobOut(
        id=str(j.id),
        kind=JobKind(j.kind),
        ref_id=str(j.ref_id) if j.ref_id else None,
        status=JobStatus(j.status),
        progress=j.progress,
        stage=j.stage,
        message=j.message,
        error=j.error,
        external_id=j.external_id,
        seed=j.seed,
        started_at=j.started_at,
        finished_at=j.finished_at,
        params=j.params,
        created_at=j.created_at,
    )


def enqueue(
    db: Session,
    kind: str,
    ref_id: uuid.UUID | None,
    params: dict[str, Any] | None,
    user: str | None,
) -> m.Job:
    j = m.Job(kind=kind, ref_id=ref_id, status="queued", params=params, created_by=user)
    db.add(j)
    db.commit()
    try:
        from groma_api.queue import submit

        submit(j.id)
    except Exception as exc:
        j.message = f"queued (worker not reachable: {exc})"
        db.commit()
    return j


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(_: CurrentUser, db: DB, limit: int = 100) -> list[JobOut]:
    return [
        to_job(j) for j in db.scalars(select(m.Job).order_by(m.Job.created_at.desc()).limit(limit))
    ]


@router.get("/jobs/{job_id}", response_model=JobOut)
def read_job(job_id: uuid.UUID, _: CurrentUser, db: DB) -> JobOut:
    j = db.get(m.Job, job_id)
    if j is None:
        raise HTTPException(404, "no such job")
    return to_job(j)


@router.get("/jobs/{job_id}/log", response_model=list[LogLine])
def read_log(
    job_id: uuid.UUID, _: CurrentUser, db: DB, after: int = 0, limit: int = 2000
) -> list[LogLine]:
    rows = db.scalars(
        select(m.JobLog)
        .where(m.JobLog.job_id == job_id, m.JobLog.id > after)
        .order_by(m.JobLog.id)
        .limit(limit)
    )
    return [LogLine(at=r.at, line=r.line) for r in rows]


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: uuid.UUID, _: Surveyor, db: DB) -> JobOut:
    j = db.get(m.Job, job_id)
    if j is None:
        raise HTTPException(404, "no such job")
    if j.status in ("succeeded", "failed", "cancelled"):
        raise HTTPException(409, f"job is already {j.status}")
    j.status = "cancelled"
    j.finished_at = datetime.now(UTC)
    db.commit()
    return to_job(j)


@router.websocket("/ws/jobs/{job_id}")
async def job_stream(ws: WebSocket, job_id: uuid.UUID) -> None:
    """Progress frames plus console lines, by polling the row. Cheap, restart-safe."""
    await ws.accept()
    last_log = 0
    last_frame: tuple[Any, ...] | None = None
    try:
        while True:
            db = SessionLocal()()
            try:
                j = db.get(m.Job, job_id)
                if j is None:
                    await ws.send_json({"error": "no such job"})
                    return
                frame = (j.status, round(j.progress, 4), j.stage, j.message)
                if frame != last_frame:
                    await ws.send_json(
                        {
                            "type": "progress",
                            "job_id": str(j.id),
                            "status": j.status,
                            "progress": j.progress,
                            "stage": j.stage,
                            "message": j.message,
                            "error": j.error,
                        }
                    )
                    last_frame = frame
                for r in db.scalars(
                    select(m.JobLog)
                    .where(m.JobLog.job_id == job_id, m.JobLog.id > last_log)
                    .order_by(m.JobLog.id)
                    .limit(500)
                ):
                    await ws.send_json(
                        {"type": "log", "id": r.id, "at": r.at.isoformat(), "line": r.line}
                    )
                    last_log = r.id
                if j.status in ("succeeded", "failed", "cancelled"):
                    await ws.send_json({"type": "end", "status": j.status})
                    return
            finally:
                db.close()
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
