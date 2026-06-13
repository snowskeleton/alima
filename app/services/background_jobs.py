"""Background job service for non-blocking operations."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from ..database import SessionLocal
from ..models import BackgroundJob, JobStatus

logger = logging.getLogger(__name__)


class BackgroundJobService:
    """Service for submitting and tracking background jobs."""

    _executor = ThreadPoolExecutor(max_workers=2)

    @classmethod
    def create_job(cls, db, job_type: str, meta: dict | None = None) -> BackgroundJob:
        """Create a new pending job record."""
        job = BackgroundJob(
            job_type=job_type,
            status=JobStatus.PENDING,
            meta=meta,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @classmethod
    def submit(cls, job_id: int, target, *args):
        """Submit a job to the thread pool executor.

        Args:
            job_id: ID of the BackgroundJob row to track.
            target: Callable(db, job, *args) that performs the work.
            *args: Extra arguments forwarded to target.
        """
        cls._executor.submit(cls._run_wrapper, job_id, target, *args)

    @staticmethod
    def _run_wrapper(job_id: int, target, *args):
        """Execute a job target in a background thread with its own DB session."""
        db = SessionLocal()
        try:
            job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
            if not job:
                logger.error(f"Background job {job_id} not found")
                return

            job.status = JobStatus.RUNNING
            db.commit()

            result = target(db, job, *args)

            job.status = JobStatus.COMPLETED
            job.result = result
            job.completed_at = datetime.utcnow()
            db.commit()

            logger.info(f"Background job {job_id} ({job.job_type}) completed")

        except Exception as e:
            logger.error(f"Background job {job_id} failed: {e}", exc_info=True)
            try:
                db.rollback()
                job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
                if job:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)[:500]
                    job.completed_at = datetime.utcnow()
                    db.commit()
            except Exception:
                logger.error(f"Failed to mark job {job_id} as failed", exc_info=True)
        finally:
            db.close()
