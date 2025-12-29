"""Routes for matching unassigned audiobook files to library books."""

from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models import Book, User
from ..services.book_matcher import BookMatcherService
from ..utils.flash import flash

router = APIRouter(prefix="/admin/match-books", tags=["Admin - Matching"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def match_books_page(
    request: Request,
    threshold: float = Query(85.0, ge=50.0, le=100.0, description="Confidence threshold"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Display the book matching page."""
    from ..utils.flash import get_flashed_messages

    matcher_service = BookMatcherService(db)

    # Get matches
    matches = matcher_service.find_matches(threshold=threshold)

    # Get all books without files for manual dropdown
    available_books = (
        db.query(Book)
        .filter(Book.file_path.is_(None))
        .order_by(Book.title)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/match_books.html",
        context={
            "current_user": current_user,
            "matched_files": matches["matched"],
            "unmatched_files": matches["unmatched"],
            "available_books": available_books,
            "threshold": threshold,
            "messages": get_flashed_messages(request),
        },
    )


@router.post("/{filename}/confirm/{book_id}")
async def confirm_match(
    request: Request,
    filename: str,
    book_id: int,
    update_metadata: bool = Form(False),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Confirm a match between a file and a book."""
    matcher_service = BookMatcherService(db)

    try:
        book = matcher_service.confirm_match(
            filename=filename,
            book_id=book_id,
            update_metadata=update_metadata,
        )

        metadata_msg = " and updated metadata" if update_metadata else ""
        flash(
            request,
            f"Successfully matched '{filename}' to '{book.title}'{metadata_msg}!",
            "success",
        )
    except ValueError as e:
        flash(request, f"Error: {str(e)}", "error")
    except Exception as e:
        flash(request, f"Unexpected error: {str(e)}", "error")

    return RedirectResponse(
        url="/admin/match-books",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{filename}/import-new")
async def import_as_new_book(
    request: Request,
    filename: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Import an unmatched file as a new book entry."""
    matcher_service = BookMatcherService(db)

    try:
        book = matcher_service.import_as_new(filename=filename)

        flash(
            request,
            f"Successfully imported '{filename}' as new book: '{book.title}'!",
            "success",
        )
    except ValueError as e:
        flash(request, f"Error: {str(e)}", "error")
    except Exception as e:
        flash(request, f"Unexpected error: {str(e)}", "error")

    return RedirectResponse(
        url="/admin/match-books",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/batch-confirm")
async def batch_confirm_matches(
    request: Request,
    threshold: float = Form(85.0),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Confirm all auto-matched files at once."""
    matcher_service = BookMatcherService(db)

    # Get matches
    matches = matcher_service.find_matches(threshold=threshold)

    success_count = 0
    error_count = 0

    for match in matches["matched"]:
        try:
            matcher_service.confirm_match(
                filename=match["filename"],
                book_id=match["matched_book"].id,
                update_metadata=False,  # Don't update metadata in batch
            )
            success_count += 1
        except Exception as e:
            error_count += 1
            # Log but continue with other files

    if success_count > 0:
        flash(
            request,
            f"Successfully matched {success_count} file(s)!",
            "success",
        )
    if error_count > 0:
        flash(
            request,
            f"Failed to match {error_count} file(s). Check logs for details.",
            "error",
        )

    return RedirectResponse(
        url="/admin/match-books",
        status_code=status.HTTP_303_SEE_OTHER,
    )
