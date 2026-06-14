"""API v2 routes for library audit."""

import asyncio
import json
import logging
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from rapidfuzz import fuzz
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ...config import settings
from ...database import SessionLocal, get_db
from ...dependencies import require_admin
from ...models import AuditResult, AuditRun, AuditStatus, Book, User
from ...services.metadata import MetadataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["Audit"])

MATCH_THRESHOLD = 70
BATCH_SIZE = 20

_executor = ThreadPoolExecutor(max_workers=1)


def _sanitize_filename(filename: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")
    if len(filename) > 200:
        filename = filename[:200]
    return filename.strip()


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
            if book.subtitle:
                db_title = f"{db_title}: {book.subtitle}"
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
                    fuzz.partial_ratio(db_title.lower(), file_title.lower())
                    if db_title and file_title
                    else 0
                )
                author_score = (
                    fuzz.partial_ratio(db_author.lower(), file_author.lower())
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

            if len(pending_results) >= BATCH_SIZE:
                db.add_all(pending_results)
                audit_run.progress = i + 1
                audit_run.mismatches = mismatches
                audit_run.missing_files = missing_files
                db.commit()
                pending_results = []

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
    """Unmatch a file from its book and rename it based on embedded metadata."""
    book = db.query(Book).filter(Book.file_path == file_path).first()
    if not book:
        return JSONResponse({"error": "No book found with that file path"}, status_code=404)

    full_path = Path(file_path)
    if not full_path.is_absolute():
        full_path = settings.audiobooks_path.parent / full_path

    old_title = book.title

    book.file_path = None
    book.file_size = None
    book.downloaded_at = None

    new_path_str = None

    if full_path.exists():
        metadata = MetadataService.read_metadata(full_path)
        file_title = metadata.get("title") or ""
        clean_title = re.sub(r"\s*\(Unabridged\)\s*$", "", file_title, flags=re.IGNORECASE).strip()

        if clean_title:
            ext = full_path.suffix
            safe_title = _sanitize_filename(clean_title)
            new_filename = f"{safe_title}{ext}"
            new_path = settings.audiobooks_path / new_filename

            counter = 1
            while new_path.exists() and new_path != full_path:
                new_filename = f"{safe_title}_{counter}{ext}"
                new_path = settings.audiobooks_path / new_filename
                counter += 1

            if new_path != full_path:
                shutil.move(str(full_path), str(new_path))
                new_path_str = str(new_path.relative_to(settings.audiobooks_path.parent))
                logger.info(f"Renamed '{full_path.name}' -> '{new_path.name}'")
            else:
                new_path_str = file_path
        else:
            new_path_str = file_path
            logger.warning(f"No embedded title found, file not renamed: {full_path.name}")

    db.commit()

    return JSONResponse({
        "success": True,
        "old_title": old_title,
        "new_file_path": new_path_str,
    })
