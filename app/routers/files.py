"""Routes for serving static files (audiobooks, covers)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Book

router = APIRouter(prefix="/files", tags=["Files"])


@router.get("/audiobooks/{book_id}.{ext}")
async def serve_audiobook(
    book_id: int,
    ext: str,
    db: Session = Depends(get_db),
):
    """
    Serve audiobook file.

    Public endpoint (no authentication required).
    """
    # Get book
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with ID {book_id} not found",
        )

    # Construct file path
    file_path = Path(book.file_path)

    # If file_path is relative, make it absolute relative to audiobooks_path parent
    if not file_path.is_absolute():
        file_path = settings.audiobooks_path.parent / file_path

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio file not found: {file_path}",
        )

    # Determine media type
    media_types = {
        "m4a": "audio/mp4",
        "m4b": "audio/x-m4b",
        "mp3": "audio/mpeg",
    }
    media_type = media_types.get(ext.lower(), "application/octet-stream")

    # Serve file
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=f"{book.title}.{ext}",
    )


@router.get("/covers/{filepath:path}")
async def serve_cover(filepath: str):
    """
    Serve cover image.

    Public endpoint (no authentication required).
    Supports subdirectories (e.g., /covers/feeds/uuid.jpg).
    """
    # Construct full path
    file_path = settings.covers_path / filepath

    # Security check: ensure the resolved path is within covers_path
    try:
        file_path = file_path.resolve()
        covers_path_resolved = settings.covers_path.resolve()

        if not str(file_path).startswith(str(covers_path_resolved)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cover image not found: {filepath}",
        )

    # Determine media type
    ext = file_path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/webp",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=file_path,
        media_type=media_type,
    )
