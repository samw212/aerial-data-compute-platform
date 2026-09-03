"""Background jobs and their progress stream. Build spec 5, 7.

`external_id` carries the NodeODM task uuid so a worker restarted during a
four-hour reconstruction can re-attach rather than start again (build spec 19.4).
`seed` travels with the job because every randomised stage — RANSAC, DBSCAN,
synthetic noise — must be reproducible from the job record (build spec 18).
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobKind(StrEnum):
    INGEST = "ingest"
    RECONSTRUCT = "reconstruct"
    IMPORT = "import"
    TILE = "tile"
    EXTRACT = "extract"
    COVERAGE = "coverage"
    OPTIMISE = "optimise"
    REPORT = "report"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(BaseModel):
    id: str
    kind: JobKind
    ref_id: str | None = None
    """The survey, scenario or coverage run this job is about."""
    status: JobStatus = JobStatus.QUEUED
    progress: float = Field(default=0.0, ge=0, le=1)
    stage: str | None = None
    message: str | None = None
    error: str | None = None
    external_id: str | None = None
    seed: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def terminal(self) -> bool:
        return self.status in (
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        )


class JobProgress(BaseModel):
    """One frame of the WS /ws/jobs/{id} stream."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    status: JobStatus
    progress: float = Field(ge=0, le=1)
    stage: str | None = None
    message: str | None = None


__all__ = ["Job", "JobKind", "JobProgress", "JobStatus"]
