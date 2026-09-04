"""Job handlers. One function per JobKind; each receives a JobContext.

Handlers write progress with ctx.progress() and console lines with ctx.log();
both go to Postgres and reach the browser through /ws/jobs/{id}. A handler
checks ctx.cancelled() at safe points and returns when it is set.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from groma_api.db import models as m
from groma_api.settings import Settings


@dataclass
class JobContext:
    db: Session
    job: m.Job
    settings: Settings

    def log(self, line: str) -> None:
        self.db.add(m.JobLog(job_id=self.job.id, line=line))
        self.db.commit()

    def progress(
        self, fraction: float, stage: str | None = None, message: str | None = None
    ) -> None:
        self.job.progress = max(0.0, min(1.0, fraction))
        if stage is not None:
            self.job.stage = stage
        if message is not None:
            self.job.message = message
        self.db.commit()

    def cancelled(self) -> bool:
        self.db.refresh(self.job)
        return bool(self.job.status == "cancelled")


def coverage_job(ctx: JobContext) -> None:
    """A coverage run too fine for the request thread (build spec 7)."""
    from groma_api.routers.coverage import RunRequest, run_scenario

    job = ctx.job
    scenario = ctx.db.get(m.Scenario, job.ref_id)
    if scenario is None:
        raise RuntimeError("scenario no longer exists")
    req = RunRequest.model_validate(job.params or {})
    ctx.progress(0.05, "kernel", f"grid {req.grid_spacing_m} m")
    row = run_scenario(ctx.db, ctx.settings, scenario, req, job.created_by)
    ctx.log(f"coverage run {row.id} · {row.duration_ms} ms · kernel {row.kernel_version}")
    ctx.progress(1.0, "done", f"run {row.id}")


HANDLERS: dict[str, Callable[[JobContext], None]] = {
    "coverage": coverage_job,
}
