"""Library audit routes for detecting metadata mismatches."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import require_admin
from ..models import Book, User
from ..services.metadata import MetadataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")

MATCH_THRESHOLD = 70  # Below this % is a mismatch


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(
    request: Request,
    run: bool = Query(False, description="Run the audit scan"),
    show_all: bool = Query(False, description="Show all results, not just mismatches"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Library audit page — detect metadata mismatches between files and database."""
    results = None
    summary = None

    if run:
        results, summary = _run_audit(db)
        if not show_all:
            results = [r for r in results if not r["ok"]]

    return templates.TemplateResponse(
        "admin/audit.html",
        {
            "request": request,
            "current_user": current_user,
            "results": results,
            "summary": summary,
            "run": run,
            "show_all": show_all,
        },
    )


def _run_audit(db: Session) -> tuple[list[dict], dict]:
    """Scan all books with files and compare embedded metadata against the database."""
    books = db.query(Book).filter(Book.file_path.isnot(None), Book.file_path != "").all()

    results = []
    total_scanned = 0
    mismatches = 0
    missing_files = 0

    for book in books:
        file_path = Path(book.file_path)
        if not file_path.is_absolute():
            file_path = settings.audiobooks_path.parent / file_path

        if not file_path.exists():
            missing_files += 1
            results.append({
                "book_title": book.title,
                "book_author": book.author or "",
                "file_title": None,
                "file_author": None,
                "title_score": 0,
                "author_score": 0,
                "file_path": book.file_path,
                "status": "missing",
                "ok": False,
            })
            continue

        total_scanned += 1
        metadata = MetadataService.read_metadata(file_path)

        file_title = metadata.get("title") or ""
        file_author = metadata.get("author") or ""
        db_title = book.title or ""
        db_author = book.author or ""

        title_score = fuzz.ratio(db_title.lower(), file_title.lower()) if db_title and file_title else 0
        author_score = fuzz.ratio(db_author.lower(), file_author.lower()) if db_author and file_author else 0

        is_ok = title_score >= MATCH_THRESHOLD
        if not is_ok:
            mismatches += 1

        if title_score >= MATCH_THRESHOLD:
            status = "good"
        elif title_score >= 50:
            status = "warning"
        else:
            status = "bad"

        results.append({
            "book_title": db_title,
            "book_author": db_author,
            "file_title": file_title,
            "file_author": file_author,
            "title_score": round(title_score, 1),
            "author_score": round(author_score, 1),
            "file_path": book.file_path,
            "status": status,
            "ok": is_ok,
        })

    # Sort: missing first, then by worst title score
    results.sort(key=lambda r: (0 if r["status"] == "missing" else 1, r["title_score"]))

    summary = {
        "total_scanned": total_scanned,
        "mismatches": mismatches,
        "missing_files": missing_files,
        "good": total_scanned - mismatches,
    }

    return results, summary
