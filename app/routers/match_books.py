"""Routes for matching unassigned audiobook files to library books."""

from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
    """Display the book matching page (loads quickly, results fetched via AJAX)."""
    from ..utils.flash import get_flashed_messages

    return templates.TemplateResponse(
        request=request,
        name="admin/match_books.html",
        context={
            "current_user": current_user,
            "threshold": threshold,
            "messages": get_flashed_messages(request),
        },
    )


@router.get("/api/matches", response_class=JSONResponse)
async def get_matches(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """API endpoint to fetch all unassigned files with their best matches."""
    matcher_service = BookMatcherService(db)

    # Get all matches (using low threshold to include all suggestions)
    matches = matcher_service.find_matches(threshold=0)

    # Get all books without files for manual dropdown
    available_books = (
        db.query(Book)
        .filter(Book.file_path.is_(None))
        .order_by(Book.title)
        .all()
    )

    # Combine all files into unified list
    all_files = []

    # Add matched files
    for match in matches["matched"]:
        all_files.append({
            "filename": match["filename"],
            "file_size": match["file_size"],
            "metadata": match["metadata"] or {},
            "suggested_book": {
                "id": match["matched_book"].id,
                "title": match["matched_book"].title,
                "author": match["matched_book"].author,
                "series": match["matched_book"].series,
                "series_position": match["matched_book"].series_position,
            },
            "confidence": match["confidence"],
        })

    # Add unmatched files (which may still have suggestions below threshold)
    for file in matches["unmatched"]:
        file_data = {
            "filename": file["filename"],
            "file_size": file["file_size"],
            "metadata": file["metadata"] or {},
            "confidence": file.get("confidence", 0),
        }
        if file.get("suggested_book"):
            file_data["suggested_book"] = {
                "id": file["suggested_book"].id,
                "title": file["suggested_book"].title,
                "author": file["suggested_book"].author,
            }
        else:
            file_data["suggested_book"] = None
        all_files.append(file_data)

    books_data = [
        {
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "series": book.series,
            "series_position": book.series_position,
        }
        for book in available_books
    ]

    return {
        "files": all_files,
        "available_books": books_data,
    }


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


@router.post("/batch-import-unmatched")
async def batch_import_unmatched(
    request: Request,
    threshold: float = Form(85.0),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Import all unmatched files as new books."""
    matcher_service = BookMatcherService(db)

    # Get matches
    matches = matcher_service.find_matches(threshold=threshold)

    success_count = 0
    error_count = 0

    for file in matches["unmatched"]:
        try:
            matcher_service.import_as_new(filename=file["filename"])
            success_count += 1
        except Exception as e:
            error_count += 1
            # Log but continue with other files

    if success_count > 0:
        flash(
            request,
            f"Successfully imported {success_count} file(s) as new books!",
            "success",
        )
    if error_count > 0:
        flash(
            request,
            f"Failed to import {error_count} file(s). Check logs for details.",
            "error",
        )

    return RedirectResponse(
        url="/admin/match-books",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{filename}/delete")
async def delete_unassigned_file(
    request: Request,
    filename: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete an unassigned audiobook file."""
    from pathlib import Path
    from ..config import settings

    # Define the unassigned directory
    unassigned_dir = settings.audiobooks_path / "unassigned"
    file_path = unassigned_dir / filename

    # Check if file exists
    if not file_path.exists():
        return JSONResponse(
            content={"error": "File not found"},
            status_code=404,
        )

    try:
        # Delete the file
        file_path.unlink()
        return JSONResponse(
            content={"success": True, "message": f"File '{filename}' deleted successfully"},
            status_code=200,
        )
    except Exception as e:
        return JSONResponse(
            content={"error": f"Failed to delete file: {str(e)}"},
            status_code=500,
        )
