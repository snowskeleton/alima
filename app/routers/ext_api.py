"""External REST API router for programmatic access."""

import logging
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_api_admin
from ..models import User
from ..services.book_import import BookImportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["API"])


@router.post("/books/import")
async def import_book(
    audio_file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    narrator: Optional[str] = Form(None),
    series: Optional[str] = Form(None),
    series_position: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    publisher: Optional[str] = Form(None),
    current_user: User = Depends(require_api_admin),
    db: Session = Depends(get_db),
):
    """
    Import an audiobook file via the API.

    Accepts a multipart form upload with an audio file and optional metadata.
    Reuses the same import logic as the web UI.
    """
    # Write uploaded file to a temp location
    suffix = Path(audio_file.filename).suffix if audio_file.filename else ".m4b"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            contents = await audio_file.read()
            tmp.write(contents)
            tmp_path = Path(tmp.name)

        import_service = BookImportService(db)

        book = import_service.import_book(
            tmp_path,
            title=title,
            author=author,
            narrator=narrator,
            series=series,
            series_position=series_position,
            description=description,
            publisher=publisher,
        )

        logger.info(f"API import by {current_user.email}: {book.title} (ID: {book.id})")

        return JSONResponse(content={
            "success": True,
            "book_id": book.id,
            "title": book.title,
            "author": book.author,
        })

    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)},
        )
    except Exception as e:
        logger.error(f"API import failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Import failed"},
        )
    finally:
        # Clean up temp file
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
