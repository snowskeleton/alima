"""API v2 routes for books."""

import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...config import settings
from ...database import get_db
from ...dependencies import get_current_active_user, require_admin
from ...models import Book, DownloadQueue, DownloadStatus, DownloadType, User
from ...schemas import DatabaseId
from ...services.book_download import BookDownloadService

router = APIRouter(prefix="/books", tags=["Books"])


def _book_to_dict(book: Book) -> dict:
    """Convert a Book model to a JSON-serializable dict."""
    return {
        "id": book.id,
        "asin": book.asin,
        "source": book.source.value,
        "title": book.title,
        "subtitle": book.subtitle,
        "author": book.author,
        "narrator": book.narrator,
        "series": book.series,
        "series_position": book.series_position,
        "description": book.description,
        "publisher": book.publisher,
        "publish_date": book.publish_date.isoformat() if book.publish_date else None,
        "duration_seconds": book.duration_seconds,
        "genres": book.genres,
        "cover_image_path": book.cover_image_path,
        "cover_url": book.cover_url,
        "file_path": book.file_path,
        "file_size": book.file_size,
        "file_format": book.file_format,
        "download_enabled": book.download_enabled,
        "download_unavailable": book.download_unavailable,
        "download_error_message": book.download_error_message,
        "metadata_source": book.metadata_source.value,
        "metadata_override": book.metadata_override,
        "added_at": book.added_at.isoformat() if book.added_at else None,
        "downloaded_at": book.downloaded_at.isoformat() if book.downloaded_at else None,
        "purchased_at": book.purchased_at.isoformat() if book.purchased_at else None,
        "audible_account_id": book.audible_account_id,
    }


@router.get("")
async def list_books(
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    source: Optional[str] = Query(None),
    series_filter: Optional[str] = Query(None),
    sort: str = Query("added_at"),
    order: str = Query("desc"),
    limit: int = Query(50, le=200),
    # Upper bound for the same reason as DatabaseId: an offset wider than a
    # 64-bit integer overflows the database driver instead of returning an
    # empty page.
    offset: int = Query(0, ge=0, le=2**63 - 1),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get paginated books with search/filter/sort."""
    query = db.query(Book)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Book.title.ilike(search_term))
            | (Book.author.ilike(search_term))
            | (Book.series.ilike(search_term))
            | (Book.narrator.ilike(search_term))
        )

    if status_filter == "downloaded":
        query = query.filter(Book.file_path.isnot(None))
    elif status_filter == "pending":
        query = query.filter(
            Book.file_path.is_(None),
            Book.download_enabled == True,
            Book.download_unavailable == False,
        )
    elif status_filter == "disabled":
        query = query.filter(
            Book.file_path.is_(None),
            Book.download_enabled == False,
        )
    elif status_filter == "unavailable":
        query = query.filter(Book.download_unavailable == True)

    if source:
        query = query.filter(Book.source == source)

    if series_filter == "series":
        query = query.filter(Book.series.isnot(None))
    elif series_filter == "standalone":
        query = query.filter(Book.series.is_(None))

    total_count = query.count()

    sort_column = getattr(Book, sort, Book.added_at)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    books = query.offset(offset).limit(limit).all()

    return {
        "books": [_book_to_dict(b) for b in books],
        "total": total_count,
        "offset": offset,
        "limit": limit,
    }


class BulkActionRequest(BaseModel):
    action: str
    book_ids: List[int]


@router.post("/bulk")
async def bulk_action(
    body: BulkActionRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Perform a bulk action on multiple books."""
    valid_actions = {"download", "enable_download", "disable_download", "delete"}
    if body.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action: {body.action}")

    if body.action == "delete" and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required for delete")

    books = db.query(Book).filter(Book.id.in_(body.book_ids)).all()
    affected = 0

    if body.action == "download":
        download_service = BookDownloadService(db)
        for book in books:
            if not book.file_path and book.source.value == "audible":
                try:
                    download_service.download_book_now(book.id)
                    affected += 1
                except ValueError:
                    pass

    elif body.action == "enable_download":
        for book in books:
            if not book.file_path:
                book.download_enabled = True
                affected += 1
        db.commit()

    elif body.action == "disable_download":
        for book in books:
            if not book.file_path:
                book.download_enabled = False
                affected += 1
        db.commit()

    elif body.action == "delete":
        for book in books:
            if book.file_path:
                file_path = Path(book.file_path)
                if not file_path.is_absolute():
                    file_path = settings.audiobooks_path.parent / file_path
                try:
                    file_path.unlink(missing_ok=True)
                except Exception:
                    pass
            if book.cover_image_path:
                cover_path = Path(book.cover_image_path)
                if not cover_path.is_absolute():
                    cover_path = settings.covers_path.parent / cover_path
                try:
                    cover_path.unlink(missing_ok=True)
                except Exception:
                    pass
            db.delete(book)
            affected += 1
        db.commit()

    return {"success": True, "affected": affected}


@router.get("/{book_id}")
async def get_book(
    book_id: DatabaseId,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get full book detail."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    data = _book_to_dict(book)

    # Include download queue info
    queue_entry = (
        db.query(DownloadQueue)
        .filter(DownloadQueue.book_id == book_id)
        .order_by(DownloadQueue.created_at.desc())
        .first()
    )
    if queue_entry:
        data["download_queue"] = {
            "id": queue_entry.id,
            "status": queue_entry.status.value,
            "error_message": queue_entry.error_message,
            "attempts": queue_entry.attempts,
            "started_at": queue_entry.started_at.isoformat() if queue_entry.started_at else None,
            "completed_at": queue_entry.completed_at.isoformat() if queue_entry.completed_at else None,
        }

    return data


@router.put("/{book_id}/metadata")
async def update_metadata(
    book_id: DatabaseId,
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update book metadata overrides."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    metadata_override = {}
    for field in ["title", "subtitle", "author", "narrator", "series",
                  "series_position", "description", "publisher"]:
        if field in body and body[field]:
            metadata_override[field] = body[field]

    book.metadata_override = metadata_override if metadata_override else None
    db.commit()

    return _book_to_dict(book)


@router.delete("/{book_id}/metadata")
async def reset_metadata(
    book_id: DatabaseId,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reset book metadata to original values."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    book.metadata_override = None
    db.commit()

    return {"success": True}


@router.post("/{book_id}/download")
async def download_book(
    book_id: DatabaseId,
    force: bool = Query(False, description="Re-queue even if an entry is already in flight"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Queue a book for download."""
    download_service = BookDownloadService(db)
    try:
        result = download_service.download_book_now(book_id, force=force)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{book_id}/unmatch")
async def unmatch_book(
    book_id: DatabaseId,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Move file back to unassigned folder."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.file_path:
        raise HTTPException(status_code=400, detail="No file to unmatch")

    file_path = Path(book.file_path)
    if not file_path.is_absolute():
        file_path = settings.audiobooks_path.parent / file_path

    filename = file_path.name
    unassigned_dir = settings.audiobooks_path / "unassigned"
    unassigned_dir.mkdir(parents=True, exist_ok=True)
    dest_path = unassigned_dir / filename

    if file_path.exists():
        shutil.move(str(file_path), str(dest_path))

    book.file_path = None
    book.file_size = None
    book.file_format = None
    book.downloaded_at = None

    if book.source.value == "audible":
        book.download_enabled = True

    db.commit()

    return {"success": True, "filename": filename}


@router.delete("/{book_id}/file")
async def delete_file(
    book_id: DatabaseId,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete the downloaded file but keep the book in library."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.file_path:
        file_path = Path(book.file_path)
        if not file_path.is_absolute():
            file_path = settings.audiobooks_path.parent / file_path
        if file_path.exists():
            file_path.unlink()

    book.file_path = None
    book.file_size = None
    book.file_format = None
    book.downloaded_at = None
    book.download_enabled = True
    book.download_unavailable = False
    book.download_error_message = None
    db.commit()

    return {"success": True}


@router.delete("/{book_id}")
async def delete_book(
    book_id: DatabaseId,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a book and its files from the library."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.file_path:
        file_path = Path(book.file_path)
        if not file_path.is_absolute():
            file_path = settings.audiobooks_path.parent / file_path
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass

    if book.cover_image_path:
        cover_path = Path(book.cover_image_path)
        if not cover_path.is_absolute():
            cover_path = settings.covers_path.parent / cover_path
        try:
            cover_path.unlink(missing_ok=True)
        except Exception:
            pass

    title = book.title
    db.delete(book)
    db.commit()

    return {"success": True, "message": f"Book '{title}' deleted"}


@router.patch("/{book_id}")
async def patch_book(
    book_id: DatabaseId,
    body: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Patch book fields (toggle download, mark available)."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if "download_enabled" in body:
        book.download_enabled = body["download_enabled"]

    if "mark_available" in body and body["mark_available"]:
        book.download_unavailable = False
        book.download_error_message = None
        book.download_enabled = True

    db.commit()

    return _book_to_dict(book)
