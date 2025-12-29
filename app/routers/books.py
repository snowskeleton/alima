"""Routes for individual book management."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_active_user, require_admin
from ..models import Book, User
from ..schemas import BookResponse

router = APIRouter(prefix="/books", tags=["Books"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/{book_id}/edit", response_class=HTMLResponse)
async def edit_book_page(
    request: Request,
    book_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Display book edit page."""
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with ID {book_id} not found",
        )

    return templates.TemplateResponse(
        request=request,
        name="books/edit.html",
        context={
            "current_user": current_user,
            "book": book,
        },
    )


@router.post("/{book_id}/update-metadata")
async def update_book_metadata(
    book_id: int,
    title: str = Form(None),
    subtitle: str = Form(None),
    author: str = Form(None),
    narrator: str = Form(None),
    series: str = Form(None),
    series_position: str = Form(None),
    description: str = Form(None),
    publisher: str = Form(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update book metadata with overrides."""
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with ID {book_id} not found",
        )

    # Build metadata override dictionary
    metadata_override = {}
    if title:
        metadata_override["title"] = title
    if subtitle:
        metadata_override["subtitle"] = subtitle
    if author:
        metadata_override["author"] = author
    if narrator:
        metadata_override["narrator"] = narrator
    if series:
        metadata_override["series"] = series
    if series_position:
        metadata_override["series_position"] = series_position
    if description:
        metadata_override["description"] = description
    if publisher:
        metadata_override["publisher"] = publisher

    # Update metadata override
    book.metadata_override = metadata_override if metadata_override else None
    db.commit()
    db.refresh(book)

    # Redirect back to library or book detail
    return RedirectResponse(
        url=f"/library/{book_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{book_id}/reset-metadata")
async def reset_book_metadata(
    book_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reset book metadata to original values."""
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with ID {book_id} not found",
        )

    # Clear metadata override
    book.metadata_override = None
    db.commit()

    return {"message": "Metadata reset to original values"}


@router.delete("/{book_id}")
async def delete_book(
    book_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a book from the library."""
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with ID {book_id} not found",
        )

    # TODO: Delete associated files (audiobook file, cover image)
    # This will be implemented when file serving is added

    db.delete(book)
    db.commit()

    return {"message": f"Book '{book.title}' deleted successfully"}
