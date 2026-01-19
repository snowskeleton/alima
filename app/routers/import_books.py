"""Routes for importing third-party audiobooks."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import require_admin
from ..models import Book, User
from ..services.book_import import BookImportService
from ..services.metadata import MetadataService

router = APIRouter(prefix="/admin/import", tags=["Import"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def import_page(
    request: Request,
    current_user: User = Depends(require_admin),
):
    """Display book import page."""
    return templates.TemplateResponse(
        request=request,
        name="admin/import.html",
        context={
            "current_user": current_user,
        },
    )


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
    """Upload and import a third-party audiobook with progress tracking."""
    import logging

    logger = logging.getLogger(__name__)

    # Validate file type
    filename = audio_file.filename
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided",
        )

    file_ext = Path(filename).suffix.lower()
    valid_formats = [".m4a", ".m4b", ".mp3"]
    if file_ext not in valid_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: {file_ext}. Supported: {', '.join(valid_formats)}",
        )

    # Save uploaded file temporarily (FastAPI already buffered it in memory/temp)
    settings.temp_path.mkdir(parents=True, exist_ok=True)
    temp_file_path = settings.temp_path / filename

    logger.info(f"Starting upload of {filename}")

    try:
        # Write uploaded file to temp location
        with open(temp_file_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)

        logger.info(f"Upload complete, file size: {temp_file_path.stat().st_size} bytes")

        # Import the book
        import_service = BookImportService(db)

        logger.info("Extracting metadata and importing book...")

        # If manual metadata provided, use it
        if title and author:
            metadata = {
                "title": title,
                "author": author,
                "narrator": narrator,
                "series": series,
                "series_position": series_position,
                "description": description,
                "publisher": publisher,
            }
            book = import_service.import_book_with_metadata(temp_file_path, metadata)
        else:
            # Otherwise extract from file
            book = import_service.import_book(
                temp_file_path,
                title=title,
                author=author,
                extract_metadata=extract_metadata,
            )

        # Clean up temp file
        temp_file_path.unlink()

        logger.info(f"Successfully imported book: {book.title} (ID: {book.id})")

        # Return JSON response for Uppy uploads
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "book_id": book.id,
                "redirect_url": f"/library/{book.id}",
                "message": f"Successfully imported {book.title}"
            }
        )

    except Exception as e:
        logger.error(f"Error importing book: {e}", exc_info=True)

        # Clean up temp file on error
        if temp_file_path.exists():
            temp_file_path.unlink()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error importing book: {str(e)}",
        )


@router.post("/update-metadata/{book_id}")
async def update_book_metadata(
    book_id: int,
    title: Optional[str] = Form(None),
    subtitle: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    narrator: Optional[str] = Form(None),
    series: Optional[str] = Form(None),
    series_position: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    publisher: Optional[str] = Form(None),
    re_extract: bool = Form(False),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update metadata for an imported book."""
    import logging

    logger = logging.getLogger(__name__)

    # Get book
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    # If re-extract requested, extract metadata from the file
    if re_extract and book.file_path:
        try:
            # Construct full file path
            full_path = settings.audiobooks_path.parent / book.file_path
            if not full_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Audio file not found",
                )

            # Extract metadata
            metadata_service = MetadataService()
            extracted_metadata = metadata_service.read_metadata(full_path)

            logger.info(f"Re-extracted metadata for book {book_id}: {extracted_metadata}")

            # Update book with extracted metadata (keep existing if not in extracted)
            if extracted_metadata.get("title"):
                book.title = extracted_metadata["title"]
            if extracted_metadata.get("subtitle"):
                book.subtitle = extracted_metadata["subtitle"]
            if extracted_metadata.get("author"):
                book.author = extracted_metadata["author"]
            if extracted_metadata.get("narrator"):
                book.narrator = extracted_metadata["narrator"]
            if extracted_metadata.get("series"):
                book.series = extracted_metadata["series"]
            if extracted_metadata.get("series_position"):
                book.series_position = extracted_metadata["series_position"]
            if extracted_metadata.get("description"):
                book.description = extracted_metadata["description"]
            if extracted_metadata.get("publisher"):
                book.publisher = extracted_metadata["publisher"]
            if extracted_metadata.get("duration_seconds"):
                book.duration_seconds = extracted_metadata["duration_seconds"]

            # Extract cover art if present
            if settings.covers_path:
                safe_title = "".join(
                    c for c in book.title if c.isalnum() or c in (" ", "-", "_")
                ).rstrip()
                cover_filename = f"{safe_title}_{book.id}.jpg"
                cover_dest_path = settings.covers_path / cover_filename

                if metadata_service.extract_cover_art(full_path, cover_dest_path):
                    book.cover_image_path = f"covers/{cover_filename}"

        except Exception as e:
            logger.error(f"Error re-extracting metadata: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error extracting metadata: {str(e)}",
            )

    # Update with provided fields (only if not None and not empty string)
    if title is not None and title.strip():
        book.title = title
    if subtitle is not None:  # Allow empty string to clear subtitle
        book.subtitle = subtitle if subtitle.strip() else None
    if author is not None and author.strip():
        book.author = author
    if narrator is not None:
        book.narrator = narrator if narrator.strip() else None
    if series is not None:
        book.series = series if series.strip() else None
    if series_position is not None:
        book.series_position = series_position if series_position.strip() else None
    if description is not None:
        book.description = description if description.strip() else None
    if publisher is not None:
        book.publisher = publisher if publisher.strip() else None

    db.commit()

    logger.info(f"Updated metadata for book {book_id}: {book.title}")

    # Redirect back to book detail page
    return RedirectResponse(
        url=f"/library/{book.id}", status_code=status.HTTP_303_SEE_OTHER
    )
