"""Routes for browsing and viewing audiobook library."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_active_user
from ..models import Book, User
from ..schemas import BookResponse
from ..services.book_download import BookDownloadService

router = APIRouter(prefix="/library", tags=["Library"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def library_index(
    request: Request,
    search: Optional[str] = Query(None, description="Search books by title, author, or series"),
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    series_filter: Optional[str] = Query(None, description="Filter by series presence"),
    sort: str = Query("added_at", description="Sort field"),
    order: str = Query("desc", description="Sort order (asc/desc)"),
    view: str = Query("grid", description="View mode (grid/list/compact)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Display library of all books (with pagination)."""
    query = db.query(Book)

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Book.title.ilike(search_term))
            | (Book.author.ilike(search_term))
            | (Book.series.ilike(search_term))
            | (Book.narrator.ilike(search_term))
        )

    # Apply status filter
    if status == "downloaded":
        query = query.filter(Book.file_path.isnot(None))
    elif status == "pending":
        query = query.filter(
            Book.file_path.is_(None),
            Book.download_enabled == True,
            Book.download_unavailable == False,
        )
    elif status == "disabled":
        query = query.filter(
            Book.file_path.is_(None),
            Book.download_enabled == False,
        )
    elif status == "unavailable":
        query = query.filter(Book.download_unavailable == True)

    # Apply source filter
    if source:
        query = query.filter(Book.source == source)

    # Apply series filter
    if series_filter == "series":
        query = query.filter(Book.series.isnot(None))
    elif series_filter == "standalone":
        query = query.filter(Book.series.is_(None))

    # Apply sorting
    sort_column = getattr(Book, sort, Book.added_at)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Get total count for display
    total_count = query.count()

    # Load only initial batch (50 books)
    initial_limit = 50
    books = query.limit(initial_limit).all()

    return templates.TemplateResponse(
        request=request,
        name="library/index.html",
        context={
            "current_user": current_user,
            "books": books,
            "total_count": total_count,
            "initial_load": len(books),
            "filters": {
                "search": search,
                "status": status,
                "source": source,
                "series_filter": series_filter,
                "sort": sort,
                "order": order,
            },
            "view": view,
        },
    )


@router.get("/api/books", response_model=list[BookResponse])
async def list_books_api(
    search: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get list of books (API endpoint)."""
    query = db.query(Book)

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Book.title.ilike(search_term))
            | (Book.author.ilike(search_term))
            | (Book.series.ilike(search_term))
        )

    # Apply pagination
    books = query.order_by(Book.added_at.desc()).offset(offset).limit(limit).all()

    return [BookResponse.model_validate(book) for book in books]


@router.get("/api/more-books", response_model=list[BookResponse])
async def load_more_books_api(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    series_filter: Optional[str] = Query(None),
    sort: str = Query("added_at"),
    order: str = Query("desc"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get paginated books with filters (for infinite scroll)."""
    query = db.query(Book)

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Book.title.ilike(search_term))
            | (Book.author.ilike(search_term))
            | (Book.series.ilike(search_term))
            | (Book.narrator.ilike(search_term))
        )

    # Apply status filter
    if status == "downloaded":
        query = query.filter(Book.file_path.isnot(None))
    elif status == "pending":
        query = query.filter(
            Book.file_path.is_(None),
            Book.download_enabled == True,
            Book.download_unavailable == False,
        )
    elif status == "disabled":
        query = query.filter(
            Book.file_path.is_(None),
            Book.download_enabled == False,
        )
    elif status == "unavailable":
        query = query.filter(Book.download_unavailable == True)

    # Apply source filter
    if source:
        query = query.filter(Book.source == source)

    # Apply series filter
    if series_filter == "series":
        query = query.filter(Book.series.isnot(None))
    elif series_filter == "standalone":
        query = query.filter(Book.series.is_(None))

    # Apply sorting
    sort_column = getattr(Book, sort, Book.added_at)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    books = query.offset(offset).limit(limit).all()

    return [BookResponse.model_validate(book) for book in books]


@router.get("/{book_id}", response_class=HTMLResponse)
async def book_detail(
    request: Request,
    book_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Display detailed information about a specific book."""
    from ..utils.flash import get_flashed_messages

    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with ID {book_id} not found",
        )

    # Get metadata considering overrides
    display_metadata = _get_display_metadata(book)

    return templates.TemplateResponse(
        request=request,
        name="library/book_detail.html",
        context={
            "current_user": current_user,
            "book": book,
            "metadata": display_metadata,
            "messages": get_flashed_messages(request),
        },
    )


@router.post("/{book_id}/download")
async def download_book_now(
    request: Request,
    book_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Trigger immediate download of a specific book."""
    from ..utils.flash import flash

    download_service = BookDownloadService(db)

    try:
        result = download_service.download_book_now(book_id)

        if result["success"]:
            flash(request, "Book queued for download! Status will update automatically below.", "success")
        else:
            flash(request, f"Download failed: {result['message']}", "error")
    except ValueError as e:
        flash(request, f"Download failed: {str(e)}", "error")
    except Exception as e:
        flash(request, "Download failed: Unexpected error occurred", "error")

    return RedirectResponse(
        url=f"/library/{book_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{book_id}/toggle-download")
async def toggle_download_enabled(
    request: Request,
    book_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Toggle the download_enabled flag for a book."""
    from ..utils.flash import flash

    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        flash(request, "Book not found", "error")
        return RedirectResponse(
            url="/library",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Toggle download_enabled
    book.download_enabled = not book.download_enabled
    db.commit()

    status_msg = "enabled" if book.download_enabled else "disabled"
    flash(request, f"Auto-download {status_msg} successfully!", "success")

    return RedirectResponse(
        url=f"/library/{book_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{book_id}/mark-available")
async def mark_book_available(
    request: Request,
    book_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Clear the download_unavailable flag to allow retry."""
    from ..utils.flash import flash

    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        flash(request, "Book not found", "error")
        return RedirectResponse(
            url="/library",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Clear unavailable status
    book.download_unavailable = False
    book.download_error_message = None
    book.download_enabled = True  # Enable auto-download too
    db.commit()

    flash(request, "Book marked as available. It will be retried on the next download cycle.", "success")

    return RedirectResponse(
        url=f"/library/{book_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{book_id}/delete")
async def delete_book(
    request: Request,
    book_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete the downloaded file but keep the book in the library."""
    from pathlib import Path
    from ..utils.flash import flash
    from ..config import settings

    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        flash(request, "Book not found", "error")
        return RedirectResponse(
            url="/library",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    book_title = book.title

    # Delete physical file if it exists
    if book.file_path:
        file_path = Path(book.file_path)
        if not file_path.is_absolute():
            file_path = settings.audiobooks_path / file_path

        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                flash(request, f"Warning: Could not delete file: {e}", "warning")

    # Clear file-related fields but keep the book
    book.file_path = None
    book.file_size = None
    book.file_format = None
    book.downloaded_at = None

    # Re-enable downloads
    book.download_enabled = True

    # Clear unavailable status if it was set
    book.download_unavailable = False
    book.download_error_message = None

    db.commit()

    flash(request, f"File deleted for '{book_title}'. Book remains in library for re-download.", "success")

    return RedirectResponse(
        url=f"/library/{book_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{book_id}/unmatch")
async def unmatch_book_file(
    request: Request,
    book_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Move the file back to unassigned folder and unmatch it from the book."""
    from pathlib import Path
    from ..utils.flash import flash
    from ..config import settings
    import shutil

    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        flash(request, "Book not found", "error")
        return RedirectResponse(
            url="/library",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not book.file_path:
        flash(request, "No file to unmatch", "error")
        return RedirectResponse(
            url=f"/library/{book_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    book_title = book.title

    # Get the current file path
    file_path = Path(book.file_path)
    if not file_path.is_absolute():
        file_path = settings.audiobooks_path / file_path

    # Get the filename
    filename = file_path.name

    # Define the unassigned directory
    unassigned_dir = settings.audiobooks_path / "unassigned"
    unassigned_dir.mkdir(parents=True, exist_ok=True)

    # Define the destination path
    dest_path = unassigned_dir / filename

    # Move the file if it exists
    if file_path.exists():
        try:
            shutil.move(str(file_path), str(dest_path))
        except Exception as e:
            flash(request, f"Error moving file: {e}", "error")
            return RedirectResponse(
                url=f"/library/{book_id}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
    else:
        flash(request, "File not found on disk, but database will be updated", "warning")

    # Clear file-related fields
    book.file_path = None
    book.file_size = None
    book.file_format = None
    book.downloaded_at = None

    # Re-enable downloads if it's from Audible
    if book.source.value == "audible":
        book.download_enabled = True

    db.commit()

    flash(request, f"File '{filename}' moved to unassigned folder. You can now match it to a different book.", "success")

    return RedirectResponse(
        url=f"/library/{book_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/api/books/{book_id}", response_model=BookResponse)
async def get_book_api(
    book_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get a specific book (API endpoint)."""
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with ID {book_id} not found",
        )

    return BookResponse.model_validate(book)


def _get_display_metadata(book: Book) -> dict:
    """
    Get display metadata for a book, applying any overrides.

    Args:
        book: Book model instance

    Returns:
        Dictionary of metadata to display
    """
    metadata = {
        "title": book.title,
        "subtitle": book.subtitle,
        "author": book.author,
        "narrator": book.narrator,
        "series": book.series,
        "series_position": book.series_position,
        "description": book.description,
        "publisher": book.publisher,
        "publish_date": book.publish_date,
        "duration_seconds": book.duration_seconds,
        "genres": book.genres,
    }

    # Apply metadata overrides if present
    if book.metadata_override:
        metadata.update(book.metadata_override)

    return metadata
