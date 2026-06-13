"""API v2 routes for book import."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ...config import settings
from ...database import get_db
from ...dependencies import require_admin
from ...models import Book, User
from ...services.background_jobs import BackgroundJobService
from ...services.book_import import BookImportService
from ...services.metadata import MetadataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["Import"])


@router.post("/upload")
async def upload_book(
    audio_file: UploadFile = File(...),
    title: str = Form(None),
    author: str = Form(None),
    narrator: str = Form(None),
    series: str = Form(None),
    series_position: str = Form(None),
    description: str = Form(None),
    publisher: str = Form(None),
    extract_metadata: bool = Form(True),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Upload and import a book in the background. Returns job_id."""
    filename = audio_file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    file_ext = Path(filename).suffix.lower()
    valid_formats = [".m4a", ".m4b", ".mp3"]
    if file_ext not in valid_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {file_ext}. Supported: {', '.join(valid_formats)}",
        )

    settings.temp_path.mkdir(parents=True, exist_ok=True)
    temp_file_path = settings.temp_path / filename

    with open(temp_file_path, "wb") as f:
        content = await audio_file.read()
        f.write(content)

    def _import_job(job_db, job):
        import_service = BookImportService(job_db)
        book = import_service.import_book(
            temp_file_path,
            title=title,
            author=author,
            narrator=narrator,
            series=series,
            series_position=series_position,
            description=description,
            publisher=publisher,
            extract_metadata=extract_metadata,
        )
        if temp_file_path.exists():
            temp_file_path.unlink()
        return {"book_id": book.id, "title": book.title}

    job = BackgroundJobService.create_job(db, "import", meta={"filename": filename})
    BackgroundJobService.submit(job.id, _import_job)

    return {"job_id": job.id}


@router.put("/{book_id}/metadata")
async def update_import_metadata(
    book_id: int,
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update metadata for an imported book."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    for field in ["title", "subtitle", "author", "narrator", "series",
                  "series_position", "description", "publisher"]:
        if field in body:
            val = body[field]
            if val is not None and isinstance(val, str) and val.strip():
                setattr(book, field, val)
            elif val is not None and isinstance(val, str) and not val.strip():
                setattr(book, field, None)

    db.commit()

    from .books import _book_to_dict
    return _book_to_dict(book)
