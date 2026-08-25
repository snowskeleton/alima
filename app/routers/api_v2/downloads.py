"""API v2 routes for download queue management."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, contains_eager

from ...database import get_db
from ...dependencies import require_admin
from ...models import AudibleAccount, Book, DownloadQueue, DownloadStatus, User
from ...schemas import DatabaseId
from ...services.background_jobs import BackgroundJobService
from ...services.book_download import (
    IN_FLIGHT_STATUSES,
    BookDownloadService,
    entry_eta_seconds,
    entry_idle_for,
    is_entry_stale,
)

router = APIRouter(prefix="/downloads", tags=["Downloads"])

# Pseudo-status: entries whose worker is gone. Not a DownloadStatus value, but
# the thing you actually want to search for when downloads go quiet.
STALLED_FILTER = "stalled"


def _resolve_status(status_filter: str) -> Optional[DownloadStatus]:
    """
    Map a status query value onto a DownloadStatus, case-insensitively.

    The API emits `status.value` (lowercase) while SQLAlchemy persists the enum
    by name (uppercase), so clients reasonably send either. Accept both rather
    than silently returning nothing.
    """
    try:
        return DownloadStatus(status_filter.strip().lower())
    except ValueError:
        try:
            return DownloadStatus[status_filter.strip().upper()]
        except KeyError:
            return None


def _entry_to_dict(entry: DownloadQueue) -> dict:
    return {
        "id": entry.id,
        "book_id": entry.book_id,
        "book_title": entry.book.title if entry.book else None,
        "book_author": entry.book.author if entry.book else None,
        "audible_account_id": entry.audible_account_id,
        "account_username": entry.audible_account.username if entry.audible_account else None,
        "asin": entry.asin,
        "download_type": entry.download_type.value,
        "status": entry.status.value,
        "stalled": is_entry_stale(entry),
        "bytes_downloaded": entry.bytes_downloaded,
        "total_bytes": entry.total_bytes,
        "progress_at": entry.progress_at.isoformat() if entry.progress_at else None,
        "idle_seconds": (
            int(idle.total_seconds())
            if entry.status in IN_FLIGHT_STATUSES and (idle := entry_idle_for(entry))
            else None
        ),
        "eta_seconds": entry_eta_seconds(entry),
        "priority": entry.priority,
        "error_message": entry.error_message,
        "attempts": entry.attempts,
        "file_size_bytes": entry.file_size_bytes,
        "duration_seconds": entry.duration_seconds,
        "download_speed_kbps": entry.download_speed_kbps,
        "download_quality": entry.download_quality,
        "read": entry.read,
        "read_at": entry.read_at.isoformat() if entry.read_at else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "started_at": entry.started_at.isoformat() if entry.started_at else None,
        "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
    }


def _build_stats(db: Session) -> dict:
    """
    Queue-wide counts, one bucket per status plus the stalled pseudo-status.

    Counted in SQL rather than by loading the queue into Python: the page polls
    this while downloads are running, and the queue only ever grows.
    """
    # One bucket per real status: pending, downloading, decrypting, completed, failed.
    stats = {status.value: 0 for status in DownloadStatus}

    by_status = (
        db.query(DownloadQueue.status, func.count(DownloadQueue.id))
        .group_by(DownloadQueue.status)
        .all()
    )
    for status, count in by_status:
        stats[status.value] = count

    stats["total"] = sum(stats[status.value] for status in DownloadStatus)
    stats["unread"] = (
        db.query(func.count(DownloadQueue.id))
        .filter(DownloadQueue.read == False)  # noqa: E712
        .scalar()
        or 0
    )
    # Downloading + decrypting: one "in progress" bucket for the UI tile.
    stats["in_flight"] = sum(stats[s.value] for s in IN_FLIGHT_STATUSES)

    # Staleness is an elapsed-time judgement, not a column comparison, and the
    # timestamps are a mix of naive and aware depending on when they were
    # written. Evaluate it in Python — but only over the in-flight rows, which
    # are bounded by the concurrency limit rather than by queue size.
    in_flight = (
        db.query(DownloadQueue)
        .filter(DownloadQueue.status.in_(IN_FLIGHT_STATUSES))
        .all()
    )
    stats["stalled"] = sum(1 for e in in_flight if is_entry_stale(e))

    return stats


@router.get("")
async def list_downloads(
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    read_status: str = Query("unread"),
    account: Optional[str] = Query(None),
    book_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get download queue with filtering and sorting."""
    # contains_eager, not a bare join: _entry_to_dict reads entry.book and
    # entry.audible_account, which would otherwise fire two extra queries per
    # row. The page polls this endpoint, so that N+1 lands repeatedly.
    query = (
        db.query(DownloadQueue)
        .join(Book, DownloadQueue.book_id == Book.id)
        .join(AudibleAccount, DownloadQueue.audible_account_id == AudibleAccount.id)
        .options(
            contains_eager(DownloadQueue.book),
            contains_eager(DownloadQueue.audible_account),
        )
    )

    if read_status == "read":
        query = query.filter(DownloadQueue.read == True)
    elif read_status == "unread":
        query = query.filter(DownloadQueue.read == False)

    stalled_only = False
    if status_filter:
        if status_filter.strip().lower() == STALLED_FILTER:
            # Staleness depends on elapsed time, which isn't expressible as a
            # column comparison here — narrow to in-flight in SQL and filter
            # the rest in Python below.
            stalled_only = True
            query = query.filter(DownloadQueue.status.in_(IN_FLIGHT_STATUSES))
        else:
            resolved = _resolve_status(status_filter)
            if resolved is None:
                return {"entries": [], "stats": _build_stats(db), "error": f"Unknown status '{status_filter}'"}
            query = query.filter(DownloadQueue.status == resolved)

    if account:
        query = query.filter(AudibleAccount.username.ilike(f"%{account}%"))

    if book_id:
        query = query.filter(DownloadQueue.book_id == book_id)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Book.title.ilike(search_term))
            | (Book.author.ilike(search_term))
            | (Book.series.ilike(search_term))
            | (AudibleAccount.username.ilike(search_term))
            | (DownloadQueue.asin.ilike(search_term))
            | (DownloadQueue.error_message.ilike(search_term))
        )

    # strptime raises ValueError on anything that isn't YYYY-MM-DD, which reached
    # the client as a 500. These are user-supplied query parameters, so a bad
    # value is a 422.
    def _parse_date(value: str, param: str) -> datetime:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {param} {value!r}. Expected format YYYY-MM-DD.",
            )

    if date_from:
        query = query.filter(
            DownloadQueue.created_at >= _parse_date(date_from, "date_from")
        )
    if date_to:
        query = query.filter(
            DownloadQueue.created_at < _parse_date(date_to, "date_to") + timedelta(days=1)
        )

    sort_column = getattr(DownloadQueue, sort, DownloadQueue.created_at)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    entries = query.all()

    if stalled_only:
        entries = [e for e in entries if is_entry_stale(e)]

    return {
        "entries": [_entry_to_dict(e) for e in entries],
        "stats": _build_stats(db),
    }


@router.post("/{queue_id}/retry")
async def retry_download(
    queue_id: DatabaseId,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reset a download to PENDING for scheduler pickup."""
    entry = db.query(DownloadQueue).filter(DownloadQueue.id == queue_id).first()
    if not entry:
        return {"error": "Entry not found"}, 404

    entry.status = DownloadStatus.PENDING
    entry.error_message = None
    entry.attempts = 0
    # A retried entry has no worker behind it yet; leaving the old started_at
    # in place would make it look stale the moment it goes in flight again.
    entry.started_at = None
    db.commit()
    return {"success": True}


@router.post("/reap-stale")
async def reap_stale(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Re-queue every download stuck in DOWNLOADING/DECRYPTING with no live worker."""
    return BookDownloadService(db).reap_stale_entries()


@router.delete("/{queue_id}")
async def remove_download(
    queue_id: DatabaseId,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove a download queue entry."""
    entry = db.query(DownloadQueue).filter(DownloadQueue.id == queue_id).first()
    if not entry:
        return {"error": "Entry not found"}, 404
    db.delete(entry)
    db.commit()
    return {"success": True}


@router.patch("/{queue_id}")
async def patch_download(
    queue_id: DatabaseId,
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Mark read/unread."""
    entry = db.query(DownloadQueue).filter(DownloadQueue.id == queue_id).first()
    if not entry:
        return {"error": "Entry not found"}, 404

    if "read" in body:
        entry.read = body["read"]
        entry.read_at = datetime.now(timezone.utc) if body["read"] else None

    db.commit()
    return _entry_to_dict(entry)


@router.post("/bulk")
async def bulk_action(
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Bulk actions: mark_read, mark_unread, remove, retry."""
    action = body.get("action")
    entry_ids = body.get("entry_ids", [])

    if not entry_ids:
        return {"success": True, "affected": 0}

    entries = db.query(DownloadQueue).filter(DownloadQueue.id.in_(entry_ids)).all()

    if action == "mark_read":
        for e in entries:
            e.read = True
            e.read_at = datetime.now(timezone.utc)
    elif action == "mark_unread":
        for e in entries:
            e.read = False
            e.read_at = None
    elif action == "retry":
        for e in entries:
            e.status = DownloadStatus.PENDING
            e.error_message = None
            e.attempts = 0
            e.started_at = None
    elif action == "remove":
        for e in entries:
            db.delete(e)

    db.commit()
    return {"success": True, "affected": len(entries)}


@router.post("/process")
async def process_queue(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Trigger queue processing in background. Returns job_id."""
    def _process_job(job_db, job):
        download_service = BookDownloadService(job_db)
        return download_service.process_queue(max_downloads=5)

    job = BackgroundJobService.create_job(db, "download_batch")
    BackgroundJobService.submit(job.id, _process_job)

    return {"job_id": job.id}


# A /stream SSE endpoint used to live here. It was never wired up, and it held
# a database session open for the lifetime of every connection while internally
# doing nothing but polling on a 5s timer. The downloads page polls GET ""
# instead, which respects the caller's filters and returns the stats alongside
# the entries. See useDownloads.ts for the cadence.
