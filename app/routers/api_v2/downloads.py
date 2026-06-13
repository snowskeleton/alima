"""API v2 routes for download queue management."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ...database import get_db
from ...dependencies import require_admin
from ...models import AudibleAccount, Book, DownloadQueue, DownloadStatus, User
from ...services.background_jobs import BackgroundJobService
from ...services.book_download import BookDownloadService

router = APIRouter(prefix="/downloads", tags=["Downloads"])


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
    query = (
        db.query(DownloadQueue)
        .join(Book, DownloadQueue.book_id == Book.id)
        .join(AudibleAccount, DownloadQueue.audible_account_id == AudibleAccount.id)
    )

    if read_status == "read":
        query = query.filter(DownloadQueue.read == True)
    elif read_status == "unread":
        query = query.filter(DownloadQueue.read == False)

    if status_filter:
        query = query.filter(DownloadQueue.status == status_filter)

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

    if date_from:
        from_date = datetime.strptime(date_from, "%Y-%m-%d")
        query = query.filter(DownloadQueue.created_at >= from_date)
    if date_to:
        to_date = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(DownloadQueue.created_at < to_date)

    sort_column = getattr(DownloadQueue, sort, DownloadQueue.created_at)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    entries = query.all()

    # Stats
    all_entries = db.query(DownloadQueue).all()
    stats = {
        "total": len(all_entries),
        "unread": sum(1 for e in all_entries if not e.read),
        "pending": sum(1 for e in all_entries if e.status == DownloadStatus.PENDING),
        "downloading": sum(1 for e in all_entries if e.status in [DownloadStatus.DOWNLOADING, DownloadStatus.DECRYPTING]),
        "failed": sum(1 for e in all_entries if e.status == DownloadStatus.FAILED),
        "completed": sum(1 for e in all_entries if e.status == DownloadStatus.COMPLETED),
    }

    return {
        "entries": [_entry_to_dict(e) for e in entries],
        "stats": stats,
    }


@router.post("/{queue_id}/retry")
async def retry_download(
    queue_id: int,
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
    db.commit()
    return {"success": True}


@router.delete("/{queue_id}")
async def remove_download(
    queue_id: int,
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
    queue_id: int,
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
    """Bulk actions: mark_read, mark_unread, remove."""
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


async def _download_sse_generator(db: Session):
    """SSE generator for download queue status updates."""
    while True:
        try:
            db.expire_all()
            entries = (
                db.query(DownloadQueue)
                .join(Book, DownloadQueue.book_id == Book.id)
                .order_by(DownloadQueue.priority.desc(), DownloadQueue.created_at)
                .all()
            )

            status_data = []
            for entry in entries:
                status_data.append({
                    "queue_id": entry.id,
                    "book_id": entry.book_id,
                    "book_title": entry.book.title if entry.book else "Unknown",
                    "asin": entry.asin,
                    "status": entry.status.value,
                    "priority": entry.priority,
                    "attempts": entry.attempts,
                    "error_message": entry.error_message,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                    "started_at": entry.started_at.isoformat() if entry.started_at else None,
                    "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
                })

            yield {"event": "queue_status", "data": json.dumps(status_data)}
            await asyncio.sleep(5)

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
            await asyncio.sleep(5)


@router.get("/stream")
async def stream_downloads(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """SSE stream for download queue status."""
    return EventSourceResponse(_download_sse_generator(db))
