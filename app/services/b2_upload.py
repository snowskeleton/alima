"""Service for uploading downloaded audiobooks and covers to Backblaze B2.

Uploads run out-of-band from the download pipeline. A book becomes eligible the
moment it has a local file but no B2 key, so this same sweep covers two cases
with one query: freshly downloaded books, and an existing library being
backfilled after B2 is first enabled.

Failed uploads leave the key null, so the next sweep retries automatically. A
small in-process failure counter stops a permanently broken file from being
retried on every pass.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import Book
from .storage import get_storage_service

logger = logging.getLogger(__name__)

# Give up on a book after this many consecutive failures within one process
# lifetime. Reset on restart, so a transient B2 outage recovers on its own.
MAX_UPLOAD_ATTEMPTS = 3

_failure_counts: dict[int, int] = {}

# Characters that make an object key awkward to turn back into a file on disk.
# "/" is excluded deliberately — it would create phantom folders in the bucket.
_UNSAFE_KEY_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')

# Object keys are capped at 1024 bytes; titles with long subtitles can be
# surprisingly close to that, so cut well short of it.
MAX_TITLE_LENGTH = 120


def safe_title(title: str | None) -> str:
    """Turn a book title into something usable as an object key component."""
    cleaned = _UNSAFE_KEY_CHARS.sub("", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")

    if len(cleaned) > MAX_TITLE_LENGTH:
        cleaned = cleaned[:MAX_TITLE_LENGTH].rstrip()

    return cleaned or "untitled"


def audio_key_for(book: Book) -> str:
    """
    Build the B2 object key for a book's audio file.

    Named after the book so the bucket is browsable and restorable on its own,
    with the id appended because titles are not unique — two editions, or a
    re-download of the same book, would otherwise overwrite each other.
    """
    return f"audiobooks/{safe_title(book.title)} [{book.id}].{book.file_format or 'm4a'}"


class B2UploadService:
    """Uploads local audiobook and cover files to B2."""

    def __init__(self, db: Session):
        self.db = db

    def find_pending(self, limit: int | None = None) -> list[Book]:
        """Books that have a local file but are missing at least one B2 key."""
        query = (
            self.db.query(Book)
            .filter(Book.file_path.isnot(None))
            .filter(
                (Book.b2_audio_key.is_(None))
                | ((Book.cover_image_path.isnot(None)) & (Book.b2_cover_key.is_(None)))
            )
            .order_by(Book.id)
        )
        if limit:
            query = query.limit(limit)

        return [
            book for book in query.all()
            if _failure_counts.get(book.id, 0) < MAX_UPLOAD_ATTEMPTS
        ]

    def upload_book(self, book: Book) -> bool:
        """
        Upload a single book's audio and cover to B2.

        Returns True if anything was uploaded, False if skipped or failed.
        """
        storage = get_storage_service()
        if not storage:
            return False

        uploaded = False

        try:
            if not book.b2_audio_key and book.file_path:
                audio_path = Path(book.file_path)
                if not audio_path.is_absolute():
                    audio_path = settings.audiobooks_path.parent / audio_path

                if audio_path.exists():
                    key = audio_key_for(book)
                    storage.upload_file(audio_path, key)
                    book.b2_audio_key = key
                    uploaded = True
                else:
                    logger.warning(
                        f"Book {book.id} '{book.title}' has file_path but no file on disk: {audio_path}"
                    )

            if book.cover_image_path and not book.b2_cover_key:
                # cover_image_path is stored relative to the data dir as "covers/<name>"
                cover_path = settings.covers_path.parent / book.cover_image_path
                if cover_path.exists():
                    storage.upload_file(cover_path, book.cover_image_path)
                    book.b2_cover_key = book.cover_image_path
                    uploaded = True

            if uploaded:
                self.db.commit()
                _failure_counts.pop(book.id, None)

            return uploaded

        except Exception as e:
            self.db.rollback()
            count = _failure_counts.get(book.id, 0) + 1
            _failure_counts[book.id] = count
            level = logger.error if count >= MAX_UPLOAD_ATTEMPTS else logger.warning
            level(
                f"B2 upload failed for book {book.id} '{book.title}' "
                f"(attempt {count}/{MAX_UPLOAD_ATTEMPTS}): {e}"
            )
            return False

    def process_pending(
        self,
        limit: int | None = None,
        max_concurrent: int = 2,
        progress_callback=None,
    ) -> dict:
        """
        Upload every book that still needs it.

        Args:
            limit: Maximum books to process this pass (None = all)
            max_concurrent: Parallel upload workers
            progress_callback: Optional fn(book, success) called after each book

        Returns:
            Stats dict with attempted/uploaded/failed counts
        """
        storage = get_storage_service()
        if not storage:
            return {"attempted": 0, "uploaded": 0, "failed": 0}

        pending = self.find_pending(limit=limit)
        stats = {"attempted": len(pending), "uploaded": 0, "failed": 0}

        if not pending:
            return stats

        logger.info(f"Uploading {len(pending)} book(s) to B2 with {max_concurrent} workers")

        # Each worker needs its own session — SQLAlchemy sessions are not
        # thread-safe, and this mirrors how BookDownloadService parallelises.
        def upload_one(book_id: int) -> bool:
            db = SessionLocal()
            try:
                book = db.query(Book).filter(Book.id == book_id).first()
                if not book:
                    return False
                return B2UploadService(db).upload_book(book)
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {executor.submit(upload_one, b.id): b for b in pending}
            for future in as_completed(futures):
                book = futures[future]
                try:
                    if future.result():
                        stats["uploaded"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as e:
                    logger.error(f"Unexpected error uploading book {book.id}: {e}", exc_info=True)
                    stats["failed"] += 1

                if progress_callback:
                    progress_callback(book, stats)

        logger.info(
            f"B2 upload pass complete: {stats['uploaded']} uploaded, {stats['failed']} failed"
        )
        return stats
