"""API v2 routes for background job tracking."""

import asyncio
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ...database import get_db
from ...dependencies import get_current_active_user
from ...models import BackgroundJob, JobStatus, User

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/{job_id}")
async def get_job(
    job_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get current status of a background job."""
    job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
    if not job:
        return {"error": "Job not found"}, 404

    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status.value,
        "progress": job.progress,
        "total": job.total,
        "result": job.result,
        "error_message": job.error_message,
        "meta": job.meta,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


async def _job_progress_generator(job_id: int, db: Session):
    """SSE generator that polls BackgroundJob and yields progress events."""
    while True:
        try:
            db.expire_all()
            job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
            if not job:
                yield {
                    "event": "job_progress",
                    "data": json.dumps({"status": "failed", "error": "Job not found"}),
                }
                return

            data = {
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status.value,
                "progress": job.progress,
                "total": job.total,
                "result": job.result,
                "error_message": job.error_message,
            }

            yield {"event": "job_progress", "data": json.dumps(data)}

            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                return

            await asyncio.sleep(0.5)

        except Exception as e:
            yield {
                "event": "job_progress",
                "data": json.dumps({"status": "failed", "error": str(e)}),
            }
            return


@router.get("/{job_id}/stream")
async def stream_job_progress(
    job_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """SSE endpoint streaming background job progress."""
    return EventSourceResponse(_job_progress_generator(job_id, db))
