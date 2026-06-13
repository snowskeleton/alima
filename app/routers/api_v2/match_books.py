"""API v2 routes for book matching."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...dependencies import require_admin
from ...models import User
from ...services.book_matcher import BookMatcherService

router = APIRouter(prefix="/match-books", tags=["Match Books"])


@router.get("/matches")
async def get_matches(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get unmatched files with potential matches."""
    matcher = BookMatcherService(db)
    matches = matcher.find_matches()
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
