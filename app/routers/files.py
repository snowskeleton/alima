"""Routes for serving static files (audiobooks, covers)."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Book
from ..services.storage import get_storage_service

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
    Redirects to a signed B2 URL when available, otherwise serves from disk.
    """
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with ID {book_id} not found",
        )

    # Redirect to B2 if the file has been uploaded there
    storage = get_storage_service()
    if storage and book.b2_audio_key:
        url = storage.get_signed_url(book.b2_audio_key)
        return RedirectResponse(url, status_code=302)

    # Fall back to local file serving
    if not book.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found",
        )

    file_path = Path(book.file_path)

    if not file_path.is_absolute():
        file_path = settings.audiobooks_path.parent / file_path

    try:
        file_path = file_path.resolve()
        audiobooks_base_resolved = settings.audiobooks_path.parent.resolve()

        if not str(file_path).startswith(str(audiobooks_base_resolved)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found",
        )

    media_types = {
        "m4a": "audio/mp4",
        "m4b": "audio/x-m4b",
        "mp3": "audio/mpeg",
    }
    media_type = media_types.get(ext.lower(), "application/octet-stream")

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

    Covers prefer the local file and fall back to B2, the opposite of
    audiobooks. Covers are small enough that serving them locally costs little
    bandwidth, and this avoids a database lookup on every request — a library
    grid view fires dozens at once. The B2 fallback still means covers keep
    working if local files are ever pruned.
    """
    file_path = settings.covers_path / filepath

    try:
        file_path = file_path.resolve()
        covers_path_resolved = settings.covers_path.resolve()

        if not str(file_path).startswith(str(covers_path_resolved)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
        )

    if not file_path.exists():
        # Local file is gone — fall back to B2 if it's configured. The B2 key
        # for a cover is always its path relative to the data dir.
        storage = get_storage_service()
        if storage:
            url = storage.get_signed_url(f"covers/{filepath}")
            return RedirectResponse(url, status_code=302)

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cover image not found: {filepath}",
        )

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
