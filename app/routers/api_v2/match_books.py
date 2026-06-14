"""API v2 routes for book matching."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...dependencies import require_admin
from ...models import Book, User
from ...services.book_matcher import BookMatcherService

router = APIRouter(prefix="/match-books", tags=["Match Books"])


@router.get("/matches")
async def get_matches(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get unmatched files with top candidate matches for each."""
    matcher = BookMatcherService(db)
    files = matcher.scan_unassigned_files()

    available_books = db.query(Book).filter(Book.file_path.is_(None)).all()

    matches = []
    for file_info in files:
        scored = []
        for book in available_books:
            raw_score = matcher._calculate_match_score(file_info["metadata"], book)
            if raw_score > 0:
                scored.append({
                    "book_id": book.id,
                    "title": book.title or "",
                    "author": book.author or "",
                    "score": round(raw_score / 100, 2),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)

        matches.append({
            "filename": file_info["filename"],
            "file_path": str(file_info["file_path"]),
            "candidates": scored[:5],
        })

    return {"matches": matches}


@router.post("/confirm")
async def confirm_match(
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Confirm a file-to-book match."""
    filename = body.get("filename")
    book_id = body.get("book_id")
    if not filename or not book_id:
        raise HTTPException(status_code=400, detail="filename and book_id required")

    matcher = BookMatcherService(db)
    result = matcher.confirm_match(filename, book_id)
    return result


@router.post("/import")
async def import_as_new(
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Import an unmatched file as a new book."""
    filename = body.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="filename required")

    matcher = BookMatcherService(db)
    result = matcher.import_as_new(filename)
    return result


@router.post("/batch-confirm")
async def batch_confirm(
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Batch confirm multiple matches."""
    matches = body.get("matches", [])
    if not matches:
        return {"confirmed": 0}

    matcher = BookMatcherService(db)
    confirmed = 0
    for match in matches:
        try:
            matcher.confirm_match(match["filename"], match["book_id"])
            confirmed += 1
        except Exception:
            pass

    return {"confirmed": confirmed, "total": len(matches)}


@router.delete("/{filename}")
async def delete_unmatched(
    filename: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete an unmatched file."""
    matcher = BookMatcherService(db)
    result = matcher.delete_file(filename)
    return result
