"""Library audit routes for detecting metadata mismatches."""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from rapidfuzz import fuzz
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ..config import settings
from ..database import SessionLocal, get_db
from ..dependencies import require_admin
from ..models import AuditResult, AuditRun, AuditStatus, Book, User
from ..services.metadata import MetadataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")

MATCH_THRESHOLD = 70  # Below this % is a mismatch
BATCH_SIZE = 20  # Commit results in batches for efficiency

_executor = ThreadPoolExecutor(max_workers=1)


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Library audit page."""
    # Find the most recent completed audit run to offer "View Last Results"
    last_run = (
        db.query(AuditRun)
        .filter(AuditRun.status == AuditStatus.COMPLETED)
        .order_by(AuditRun.created_at.desc())
        .first()
    )
    # Also check for a currently running audit
    running_run = (
        db.query(AuditRun)
        .filter(AuditRun.status == AuditStatus.SCANNING)
        .order_by(AuditRun.created_at.desc())
        .first()
    )

    return templates.TemplateResponse(
        "admin/audit.html",
        {
            "request": request,
            "current_user": current_user,
            "last_run_id": last_run.id if last_run else None,
            "running_run_id": running_run.id if running_run else None,
        },
    )


@router.post("/audit/start")
async def audit_start(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Start a new audit run. Returns existing run ID if one is already scanning."""
    # Check for an already-running scan
    running = (
        db.query(AuditRun)
        .filter(AuditRun.status == AuditStatus.SCANNING)
        .first()
    )
    if running:
        return JSONResponse({"audit_id": running.id, "already_running": True})

    # Create a new audit run
    audit_run = AuditRun(status=AuditStatus.SCANNING)
    db.add(audit_run)
    db.commit()
    db.refresh(audit_run)

    audit_id = audit_run.id

    # Kick off background scan
    _executor.submit(_run_audit, audit_id)

    return JSONResponse({"audit_id": audit_id, "already_running": False})


async def _audit_progress_generator(audit_id: int, db: Session):
    """SSE generator that polls AuditRun and yields progress events."""
    while True:
        try:
            db.expire_all()
            run = db.query(AuditRun).filter(AuditRun.id == audit_id).first()
            if not run:
                yield {
                    "event": "audit_progress",
                    "data": json.dumps({"status": "failed", "error": "Audit run not found"}),
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
            logger.error(f"Error in audit progress generator: {e}", exc_info=True)
            yield {
                "event": "audit_progress",
                "data": json.dumps({"status": "failed", "error": str(e)}),
            }
            return


@router.get("/audit/stream/{audit_id}")
async def audit_stream(
    audit_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """SSE endpoint streaming audit progress."""
    return EventSourceResponse(_audit_progress_generator(audit_id, db))


@router.get("/audit/results/{audit_id}")
async def audit_results(
    audit_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return full audit results as JSON, sorted by worst match first."""
    run = db.query(AuditRun).filter(AuditRun.id == audit_id).first()
    if not run:
        return JSONResponse({"error": "Audit run not found"}, status_code=404)

    results = (
        db.query(AuditResult)
        .filter(AuditResult.audit_run_id == audit_id)
        .all()
    )

    # Sort: missing first, then by worst title score
    results.sort(key=lambda r: (0 if r.status == "missing" else 1, r.title_score))

    items = []
    for r in results:
        items.append({
            "book_title": r.book_title,
            "book_author": r.book_author,
            "file_title": r.file_title,
            "file_author": r.file_author,
            "title_score": r.title_score,
            "author_score": r.author_score,
            "file_path": r.file_path,
            "status": r.status,
        })

    summary = {
        "total_scanned": run.progress,
        "mismatches": run.mismatches,
        "missing_files": run.missing_files,
        "good": run.progress - run.mismatches - run.missing_files,
        "status": run.status.value,
    }

    return JSONResponse({"results": items, "summary": summary})


def _run_audit(audit_run_id: int):
    """Background function that performs the actual audit scan."""
    db = SessionLocal()
    try:
        audit_run = db.query(AuditRun).filter(AuditRun.id == audit_run_id).first()
        if not audit_run:
            logger.error(f"Audit run {audit_run_id} not found")
            return

        books = db.query(Book).filter(
            Book.file_path.isnot(None), Book.file_path != ""
        ).all()

        audit_run.total = len(books)
        db.commit()

        mismatches = 0
        missing_files = 0
        pending_results = []

        for i, book in enumerate(books):
            file_path = Path(book.file_path)
            if not file_path.is_absolute():
                file_path = settings.audiobooks_path.parent / file_path

            db_title = book.title or ""
            db_author = book.author or ""

            if not file_path.exists():
                missing_files += 1
                pending_results.append(AuditResult(
                    audit_run_id=audit_run_id,
                    book_title=db_title,
                    book_author=db_author,
                    file_title=None,
                    file_author=None,
                    title_score=0,
                    author_score=0,
                    file_path=book.file_path,
                    status="missing",
                ))
            else:
                metadata = MetadataService.read_metadata(file_path)

                file_title = metadata.get("title") or ""
                file_author = metadata.get("author") or ""

                title_score = (
                    fuzz.ratio(db_title.lower(), file_title.lower())
                    if db_title and file_title
                    else 0
                )
                author_score = (
                    fuzz.ratio(db_author.lower(), file_author.lower())
                    if db_author and file_author
                    else 0
                )

                if title_score >= MATCH_THRESHOLD:
                    status = "good"
                elif title_score >= 50:
                    status = "warning"
                    mismatches += 1
                else:
                    status = "bad"
                    mismatches += 1

                pending_results.append(AuditResult(
                    audit_run_id=audit_run_id,
                    book_title=db_title,
                    book_author=db_author,
                    file_title=file_title,
                    file_author=file_author,
                    title_score=round(title_score, 1),
                    author_score=round(author_score, 1),
                    file_path=book.file_path,
                    status=status,
                ))

            # Batch commit every BATCH_SIZE books
            if len(pending_results) >= BATCH_SIZE:
                db.add_all(pending_results)
                audit_run.progress = i + 1
                audit_run.mismatches = mismatches
                audit_run.missing_files = missing_files
                db.commit()
                pending_results = []

        # Flush remaining results
        if pending_results:
            db.add_all(pending_results)

        audit_run.progress = len(books)
        audit_run.mismatches = mismatches
        audit_run.missing_files = missing_files
        audit_run.status = AuditStatus.COMPLETED
        audit_run.completed_at = datetime.utcnow()
        db.commit()

        logger.info(
            f"Audit run {audit_run_id} completed: "
            f"{len(books)} scanned, {mismatches} mismatches, {missing_files} missing"
        )

    except Exception as e:
        logger.error(f"Audit run {audit_run_id} failed: {e}", exc_info=True)
        try:
            audit_run = db.query(AuditRun).filter(AuditRun.id == audit_run_id).first()
            if audit_run:
                audit_run.status = AuditStatus.FAILED
                audit_run.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            logger.error("Failed to mark audit run as failed", exc_info=True)
    finally:
        db.close()
