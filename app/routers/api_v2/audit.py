"""API v2 routes for library audit."""

import asyncio
import json
import logging

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ...database import SessionLocal, get_db
from ...dependencies import require_admin
from ...models import AuditResult, AuditRun, AuditStatus, Book, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("")
async def audit_status(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get current audit status."""
    last_run = (
        db.query(AuditRun)
        .filter(AuditRun.status == AuditStatus.COMPLETED)
        .order_by(AuditRun.created_at.desc())
        .first()
    )
    running_run = (
        db.query(AuditRun)
        .filter(AuditRun.status == AuditStatus.SCANNING)
        .order_by(AuditRun.created_at.desc())
        .first()
    )

    return {
        "last_run_id": last_run.id if last_run else None,
        "running_run_id": running_run.id if running_run else None,
    }


@router.post("/start")
async def start_audit(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Start a new audit run."""
    from ..audit import _executor, _run_audit

    running = db.query(AuditRun).filter(AuditRun.status == AuditStatus.SCANNING).first()
    if running:
        return {"audit_id": running.id, "already_running": True}

    audit_run = AuditRun(status=AuditStatus.SCANNING)
    db.add(audit_run)
    db.commit()
    db.refresh(audit_run)

    _executor.submit(_run_audit, audit_run.id)

    return {"audit_id": audit_run.id, "already_running": False}


async def _audit_progress_generator(audit_id: int, db: Session):
    """SSE generator for audit progress."""
    while True:
        try:
            db.expire_all()
            run = db.query(AuditRun).filter(AuditRun.id == audit_id).first()
            if not run:
                yield {
                    "event": "audit_progress",
                    "data": json.dumps({"status": "failed", "error": "Not found"}),
                }
                return

            data = {
                "status": run.status.value,
                "progress": run.progress,
                "total": run.total,
                "mismatches": run.mismatches,
                "missing_files": run.missing_files,
            }
            yield {"event": "audit_progress", "data": json.dumps(data)}

            if run.status in (AuditStatus.COMPLETED, AuditStatus.FAILED):
                return

            await asyncio.sleep(0.5)
        except Exception as e:
            yield {
                "event": "audit_progress",
                "data": json.dumps({"status": "failed", "error": str(e)}),
            }
            return


@router.get("/stream/{audit_id}")
async def stream_audit(
    audit_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """SSE endpoint for audit progress."""
    return EventSourceResponse(_audit_progress_generator(audit_id, db))


@router.get("/results/{audit_id}")
async def get_results(
    audit_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get full audit results."""
    run = db.query(AuditRun).filter(AuditRun.id == audit_id).first()
    if not run:
        return JSONResponse({"error": "Not found"}, status_code=404)

    results = db.query(AuditResult).filter(AuditResult.audit_run_id == audit_id).all()
    results.sort(key=lambda r: (0 if r.status == "missing" else 1, r.title_score))

    items = [
        {
            "book_title": r.book_title,
            "book_author": r.book_author,
            "file_title": r.file_title,
            "file_author": r.file_author,
            "title_score": r.title_score,
            "author_score": r.author_score,
            "file_path": r.file_path,
            "status": r.status,
        }
        for r in results
    ]

    summary = {
        "total_scanned": run.progress,
        "mismatches": run.mismatches,
        "missing_files": run.missing_files,
        "good": run.progress - run.mismatches - run.missing_files,
        "status": run.status.value,
    }

    return {"results": items, "summary": summary}


@router.post("/unmatch")
async def unmatch_file(
    file_path: str = Body(..., embed=True),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Unmatch a file from its book (delegates to audit router)."""
    from ..audit import audit_unmatch
    return await audit_unmatch(file_path=file_path, current_user=current_user, db=db)
