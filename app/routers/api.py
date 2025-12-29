"""API routes for AJAX and SSE endpoints."""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ..database import get_db
from ..dependencies import get_current_active_user
from ..models import Book, DownloadQueue, User

router = APIRouter(prefix="/api", tags=["API"])
logger = logging.getLogger(__name__)


async def queue_status_generator(
    db: Session,
    book_id: Optional[int] = None,
):
    """
    Generate SSE events with queue status updates.

    Args:
        db: Database session
        book_id: Optional book ID to filter for specific book

    Yields:
        SSE events with queue status data
    """
    while True:
        try:
            # Query queue entries
            query = db.query(DownloadQueue).join(
                Book, DownloadQueue.book_id == Book.id
            )

            if book_id:
                # Filter for specific book
                query = query.filter(DownloadQueue.book_id == book_id)

            queue_entries = query.order_by(
                DownloadQueue.priority.desc(), DownloadQueue.created_at
            ).all()

            # Build status data
            status_data = []
            for entry in queue_entries:
                book = db.query(Book).filter(Book.id == entry.book_id).first()
                status_data.append({
                    "queue_id": entry.id,
                    "book_id": entry.book_id,
                    "book_title": book.title if book else "Unknown",
                    "asin": entry.asin,
                    "status": entry.status.value,
                    "priority": entry.priority,
                    "attempts": entry.attempts,
                    "error_message": entry.error_message,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                    "started_at": entry.started_at.isoformat() if entry.started_at else None,
                    "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
                })

            # Yield SSE event
            yield {
                "event": "queue_status",
                "data": json.dumps(status_data),
            }

            # Wait 5 seconds before next update
            await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Error in queue status generator: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }
            await asyncio.sleep(5)


@router.get("/queue/stream")
async def stream_queue_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    SSE endpoint to stream all queue status updates.

    Returns:
        EventSourceResponse with real-time queue status
    """
    return EventSourceResponse(queue_status_generator(db))


@router.get("/queue/stream/{book_id}")
async def stream_book_status(
    book_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    SSE endpoint to stream status updates for a specific book.

    Args:
        book_id: ID of the book to monitor

    Returns:
        EventSourceResponse with real-time book download status
    """
    return EventSourceResponse(queue_status_generator(db, book_id=book_id))
