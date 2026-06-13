"""Routes for download queue management."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models import AudibleAccount, Book, DownloadQueue, DownloadStatus, User
from ..services.book_download import BookDownloadService

router = APIRouter(prefix="/admin/downloads", tags=["Admin - Downloads"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def download_queue(
    request: Request,
    # Filter parameters
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    read_status: str = Query("unread"),
    account: Optional[str] = Query(None),
    book_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    # Sorting parameters
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Display the download queue with filtering and sorting."""
    # Base query with joins
    query = (
        db.query(DownloadQueue)
        .join(Book, DownloadQueue.book_id == Book.id)
        .join(AudibleAccount, DownloadQueue.audible_account_id == AudibleAccount.id)
    )

    # Apply filters
    # 1. Read/unread filter (default: unread only)
    if read_status == "read":
        query = query.filter(DownloadQueue.read == True)
    elif read_status == "unread":
        query = query.filter(DownloadQueue.read == False)
    # "all" shows everything

    # 2. Status filter
    if status_filter:
        query = query.filter(DownloadQueue.status == status_filter)

    # 3. Account filter
    if account:
        query = query.filter(AudibleAccount.username.ilike(f"%{account}%"))

    # 4. Book ID filter (for linking from book pages)
    if book_id:
        query = query.filter(DownloadQueue.book_id == book_id)

    # 5. Search across multiple fields
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

    # 6. Date range filter
    if date_from:
        from_date = datetime.strptime(date_from, "%Y-%m-%d")
        query = query.filter(DownloadQueue.created_at >= from_date)
    if date_to:
        to_date = datetime.strptime(date_to, "%Y-%m-%d")
        # Include the entire day
        to_date = to_date + timedelta(days=1)
        query = query.filter(DownloadQueue.created_at < to_date)

    # Apply sorting
    sort_column = getattr(DownloadQueue, sort, DownloadQueue.created_at)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Execute query
    queue_entries = query.all()

    # Calculate statistics for all entries (ignoring filters)
    all_entries = db.query(DownloadQueue).all()
    stats = {
        "total": len(all_entries),
        "unread": len([e for e in all_entries if not e.read]),
        "pending": len([e for e in all_entries if e.status == DownloadStatus.PENDING]),
        "downloading": len([e for e in all_entries if e.status in [DownloadStatus.DOWNLOADING, DownloadStatus.DECRYPTING]]),
        "failed": len([e for e in all_entries if e.status == DownloadStatus.FAILED]),
        "completed": len([e for e in all_entries if e.status == DownloadStatus.COMPLETED]),
    }

    return templates.TemplateResponse(
        request=request,
        name="admin/downloads.html",
        context={
            "current_user": current_user,
            "queue_entries": queue_entries,
            "stats": stats,
            # Pass filter values for form population
            "filters": {
                "search": search,
                "status": status_filter,
                "read_status": read_status,
                "account": account,
                "book_id": book_id,
                "date_from": date_from,
                "date_to": date_to,
                "sort": sort,
                "order": order,
            },
        },
    )


@router.post("/{queue_id}/retry")
async def retry_download(
    queue_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Retry a failed download by resetting to PENDING. Scheduler picks it up."""
    queue_entry = db.query(DownloadQueue).filter(DownloadQueue.id == queue_id).first()
    if not queue_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Queue entry with ID {queue_id} not found",
        )

    # Reset to pending — scheduler will pick it up within 30s
    queue_entry.status = DownloadStatus.PENDING
    queue_entry.error_message = None
    queue_entry.attempts = 0
    db.commit()

    return RedirectResponse(url="/admin/downloads", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{queue_id}/remove")
async def remove_from_queue(
    queue_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove an entry from the download queue."""
    queue_entry = db.query(DownloadQueue).filter(DownloadQueue.id == queue_id).first()
    if not queue_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Queue entry with ID {queue_id} not found",
        )

    db.delete(queue_entry)
    db.commit()

    return RedirectResponse(url="/admin/downloads", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{queue_id}/mark-read")
async def mark_as_read(
    request: Request,
    queue_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Mark a queue entry as read."""
    queue_entry = db.query(DownloadQueue).filter(DownloadQueue.id == queue_id).first()
    if not queue_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue entry not found"
        )

    queue_entry.read = True
    queue_entry.read_at = datetime.now(timezone.utc)
    db.commit()

    # Redirect back to queue with current filters preserved
    referer = request.headers.get("referer", "/admin/downloads")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{queue_id}/mark-unread")
async def mark_as_unread(
    request: Request,
    queue_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Mark a queue entry as unread."""
    queue_entry = db.query(DownloadQueue).filter(DownloadQueue.id == queue_id).first()
    if not queue_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue entry not found"
        )

    queue_entry.read = False
    queue_entry.read_at = None
    db.commit()

    referer = request.headers.get("referer", "/admin/downloads")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bulk-mark-read")
async def bulk_mark_read(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Mark selected entries as read."""
    # Get form data
    form_data = await request.form()
    entry_ids_str = form_data.get("entry_ids", "")

    if not entry_ids_str:
        return RedirectResponse(url="/admin/downloads", status_code=status.HTTP_303_SEE_OTHER)

    # Parse entry IDs
    entry_ids = [int(id.strip()) for id in entry_ids_str.split(",") if id.strip()]

    # Mark entries as read
    entries = db.query(DownloadQueue).filter(DownloadQueue.id.in_(entry_ids)).all()
    for entry in entries:
        entry.read = True
        entry.read_at = datetime.now(timezone.utc)

    db.commit()

    # Redirect back with referer or default
    referer = request.headers.get("referer", "/admin/downloads")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bulk-mark-unread")
async def bulk_mark_unread(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Mark selected entries as unread."""
    # Get form data
    form_data = await request.form()
    entry_ids_str = form_data.get("entry_ids", "")

    if not entry_ids_str:
        return RedirectResponse(url="/admin/downloads", status_code=status.HTTP_303_SEE_OTHER)

    # Parse entry IDs
    entry_ids = [int(id.strip()) for id in entry_ids_str.split(",") if id.strip()]

    # Mark entries as unread
    entries = db.query(DownloadQueue).filter(DownloadQueue.id.in_(entry_ids)).all()
    for entry in entries:
        entry.read = False
        entry.read_at = None

    db.commit()

    # Redirect back with referer or default
    referer = request.headers.get("referer", "/admin/downloads")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bulk-remove")
async def bulk_remove(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove selected entries from the download queue."""
    # Get form data
    form_data = await request.form()
    entry_ids_str = form_data.get("entry_ids", "")

    if not entry_ids_str:
        return RedirectResponse(url="/admin/downloads", status_code=status.HTTP_303_SEE_OTHER)

    # Parse entry IDs
    entry_ids = [int(id.strip()) for id in entry_ids_str.split(",") if id.strip()]

    # Delete entries
    db.query(DownloadQueue).filter(DownloadQueue.id.in_(entry_ids)).delete(synchronize_session=False)
    db.commit()

    # Redirect back with referer or default
    referer = request.headers.get("referer", "/admin/downloads")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/process-queue")
async def process_queue(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Manually trigger download queue processing in background."""
    from ..services.background_jobs import BackgroundJobService

    def _process_queue_job(job_db, job):
        download_service = BookDownloadService(job_db)
        stats = download_service.process_queue(max_downloads=5)
        return stats

    job = BackgroundJobService.create_job(db, "download_batch")
    BackgroundJobService.submit(job.id, _process_queue_job)

    return RedirectResponse(
        url="/admin/downloads",
        status_code=status.HTTP_303_SEE_OTHER,
    )
