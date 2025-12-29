"""Routes for importing third-party audiobooks."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import require_admin
from ..models import User
from ..services.book_import import BookImportService

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
    """Upload and import a third-party audiobook."""
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

    # Save uploaded file temporarily
    settings.temp_path.mkdir(parents=True, exist_ok=True)
    temp_file_path = settings.temp_path / filename

    try:
        with open(temp_file_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)

        # Import the book
        import_service = BookImportService(db)

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

        # Redirect to library or book detail
        return RedirectResponse(
            url=f"/library/{book.id}", status_code=status.HTTP_303_SEE_OTHER
        )

    except Exception as e:
        # Clean up temp file on error
        if temp_file_path.exists():
            temp_file_path.unlink()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error importing book: {str(e)}",
        )
