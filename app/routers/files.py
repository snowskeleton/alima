"""Routes for serving static files (audiobooks, covers)."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Book
from ..schemas import DatabaseId
from ..services.storage import get_storage_service
from ..utils.media_types import audio_media_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["Files"])


# HEAD as well as GET: podcast players HEAD the enclosure to check size and type
# before downloading, and FastAPI's .get() registers GET only — a HEAD was 405ing,
# which players report as the episode being unavailable. The HEAD route is kept
# out of the schema so the two don't collide on one operationId.
@router.get("/audiobooks/{book_id}.{ext}")
@router.head("/audiobooks/{book_id}.{ext}", include_in_schema=False)
async def serve_audiobook(
    book_id: DatabaseId,
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

    # Redirect to B2 if the file is really there.
    #
    # The existence check is not paranoia: a b2_audio_key recorded under an older
    # key scheme points at nothing, and redirecting to a signed URL for a missing
    # object gives the client a 404 from B2 — which podcast players report as the
    # episode being deleted by the publisher. Verify, then fall through to the
    # local copy, which is the whole reason we keep one.
    #
    # 307 rather than 302: it preserves the method, so the HEAD a podcast player
    # sends before downloading stays a HEAD against B2 instead of becoming a GET.
    storage = get_storage_service()
    if storage and book.b2_audio_key:
        try:
            present = storage.file_exists(book.b2_audio_key)
        except Exception as e:
            # B2 unreachable — say nothing about the key, just serve locally.
            logger.warning(f"B2 check failed for book {book.id}, serving locally: {e}")
            present = False
        else:
            if not present:
                # Self-heal: drop the dead key so the upload scan re-uploads it
                # under the current scheme instead of failing forever.
                logger.warning(
                    f"Book {book.id} b2_audio_key {book.b2_audio_key!r} missing from "
                    f"B2; clearing it and serving the local copy"
                )
                book.b2_audio_key = None
                db.commit()

        if present:
            url = storage.get_signed_url(
                book.b2_audio_key,
                content_type=audio_media_type(book.file_format or ext),
            )
            return RedirectResponse(url, status_code=307)

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

    return FileResponse(
        path=file_path,
        media_type=audio_media_type(ext),
        filename=f"{book.title}.{ext}",
    )


@router.get("/covers/{filepath:path}")
@router.head("/covers/{filepath:path}", include_in_schema=False)
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

    # is_file() rather than exists(): a directory under covers/ exists but is not
    # servable, and handing one to FileResponse raises RuntimeError — a 500 on a
    # public, unauthenticated endpoint. Treat it as a miss.
    if not file_path.is_file():
        # Local file is gone — fall back to B2 if it's configured. The B2 key
        # for a cover is always its path relative to the data dir.
        storage = get_storage_service()
        if storage:
            url = storage.get_signed_url(f"covers/{filepath}")
            return RedirectResponse(url, status_code=307)

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cover image not found: {filepath}",
        )

    ext = file_path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=file_path,
        media_type=media_type,
    )
