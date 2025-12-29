"""Service for matching unassigned audiobook files to library books."""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Book, BookSource, MetadataSource
from .metadata import MetadataService

logger = logging.getLogger(__name__)


class BookMatcherService:
    """Service for scanning and matching unassigned audiobook files."""

    def __init__(self, db: Session):
        """Initialize the matcher service."""
        self.db = db
        self.metadata_service = MetadataService()
        self.unassigned_path = settings.audiobooks_path / "unassigned"

    def scan_unassigned_files(self) -> list[dict]:
        """
        Scan unassigned directory for audiobook files.

        Returns:
            List of dicts with file info and extracted metadata
        """
        # Ensure directory exists
        self.unassigned_path.mkdir(parents=True, exist_ok=True)

        files = []
        supported_formats = [".m4a", ".m4b", ".mp3"]

        for file_path in self.unassigned_path.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                # Extract metadata
                try:
                    metadata = self.metadata_service.read_metadata(file_path)
                except Exception as e:
                    logger.warning(f"Failed to extract metadata from {file_path.name}: {e}")
                    metadata = {}

                files.append({
                    "filename": file_path.name,
                    "file_path": file_path,
                    "file_size": file_path.stat().st_size,
                    "file_format": file_path.suffix.lower().lstrip("."),
                    "metadata": metadata,
                })

        logger.info(f"Found {len(files)} unassigned files")
        return files

    def find_matches(self, threshold: float = 85.0) -> dict:
        """
        Find matches for all unassigned files.

        Args:
            threshold: Minimum confidence score to consider a match (0-100)

        Returns:
            Dict with 'matched' and 'unmatched' file lists
        """
        unassigned_files = self.scan_unassigned_files()

        # Get all books without files
        available_books = (
            self.db.query(Book)
            .filter(Book.file_path.is_(None))
            .all()
        )

        matched = []
        unmatched = []

        for file_info in unassigned_files:
            best_match = None
            best_score = 0.0

            # Find best matching book
            for book in available_books:
                score = self._calculate_match_score(file_info["metadata"], book)
                if score > best_score:
                    best_score = score
                    best_match = book

            # Categorize based on threshold
            if best_match and best_score >= threshold:
                matched.append({
                    **file_info,
                    "matched_book": best_match,
                    "confidence": best_score,
                })
            else:
                # Include best match even if below threshold for manual review
                result = {**file_info}
                if best_match:
                    result["suggested_book"] = best_match
                    result["confidence"] = best_score
                unmatched.append(result)

        logger.info(
            f"Matching complete: {len(matched)} auto-matched, "
            f"{len(unmatched)} require manual review"
        )

        return {
            "matched": matched,
            "unmatched": unmatched,
        }

    def _calculate_match_score(self, file_metadata: dict, book: Book) -> float:
        """
        Calculate confidence score between file and book.

        Args:
            file_metadata: Extracted metadata from audio file
            book: Book model to match against

        Returns:
            Confidence score (0-100)
        """
        # Title match (70% weight)
        file_title = file_metadata.get("title", "").lower()
        book_title = book.title.lower() if book.title else ""

        if not file_title or not book_title:
            title_score = 0
        else:
            title_score = fuzz.ratio(file_title, book_title)

        # Author match (15% weight)
        file_author = file_metadata.get("author", "").lower()
        book_author = book.author.lower() if book.author else ""

        if not file_author or not book_author:
            author_score = 0
        else:
            author_score = fuzz.ratio(file_author, book_author)

        # Duration match (15% weight)
        file_duration = file_metadata.get("duration_seconds")
        book_duration = book.duration_seconds

        if file_duration and book_duration and book_duration > 0:
            # Within 5% tolerance = 100% score
            diff_pct = abs(file_duration - book_duration) / book_duration
            # 20x multiplier so 5% diff = 0 score
            duration_score = max(0, 100 - (diff_pct * 100 * 20))
        else:
            duration_score = 0

        # Weighted average
        confidence = (
            title_score * 0.7 +
            author_score * 0.15 +
            duration_score * 0.15
        )

        return round(confidence, 2)

    def confirm_match(
        self,
        filename: str,
        book_id: int,
        update_metadata: bool = False,
    ) -> Book:
        """
        Confirm a match and move file to audiobooks directory.

        Args:
            filename: Name of file in unassigned directory
            book_id: ID of book to match to
            update_metadata: Whether to update book metadata from file

        Returns:
            Updated Book model

        Raises:
            ValueError: If file or book not found
        """
        # Get book
        book = self.db.query(Book).filter(Book.id == book_id).first()
        if not book:
            raise ValueError(f"Book with ID {book_id} not found")

        if book.file_path:
            raise ValueError(f"Book already has a file: {book.file_path}")

        # Get source file
        source_file = self.unassigned_path / filename
        if not source_file.exists():
            raise ValueError(f"File not found: {filename}")

        # Generate destination filename (sanitized)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_title = self._sanitize_filename(book.title)
        file_format = source_file.suffix.lower()
        dest_filename = f"{timestamp}_{safe_title}{file_format}"

        # Handle duplicate filenames
        dest_path = settings.audiobooks_path / dest_filename
        counter = 1
        while dest_path.exists():
            dest_filename = f"{timestamp}_{safe_title}_{counter}{file_format}"
            dest_path = settings.audiobooks_path / dest_filename
            counter += 1

        # Move file
        shutil.move(str(source_file), str(dest_path))
        logger.info(f"Moved {filename} to {dest_path}")

        # Update book record
        book.file_path = str(dest_path.relative_to(settings.audiobooks_path.parent))
        book.file_size = dest_path.stat().st_size
        book.file_format = file_format.lstrip(".")
        book.downloaded_at = datetime.utcnow()

        # Update metadata if requested
        if update_metadata:
            try:
                metadata = self.metadata_service.read_metadata(dest_path)

                # Update fields from metadata
                if metadata.get("title"):
                    book.title = metadata["title"]
                if metadata.get("subtitle"):
                    book.subtitle = metadata["subtitle"]
                if metadata.get("author"):
                    book.author = metadata["author"]
                if metadata.get("narrator"):
                    book.narrator = metadata["narrator"]
                if metadata.get("series"):
                    book.series = metadata["series"]
                if metadata.get("series_position"):
                    book.series_position = metadata["series_position"]
                if metadata.get("description"):
                    book.description = metadata["description"]
                if metadata.get("publisher"):
                    book.publisher = metadata["publisher"]
                if metadata.get("duration_seconds"):
                    book.duration_seconds = metadata["duration_seconds"]
                if metadata.get("genres"):
                    book.genres = metadata["genres"]

                book.metadata_source = MetadataSource.FILE
                logger.info(f"Updated book metadata from file for book {book_id}")
            except Exception as e:
                logger.warning(f"Failed to update metadata for book {book_id}: {e}")

        # Extract cover art if book doesn't have one
        if not book.cover_image_path:
            try:
                timestamp_cover = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                cover_filename = f"{timestamp_cover}_{safe_title}.jpg"
                cover_dest_path = settings.covers_path / cover_filename

                if self.metadata_service.extract_cover_art(dest_path, cover_dest_path):
                    book.cover_image_path = f"covers/{cover_filename}"
                    logger.info(f"Extracted cover art for book {book_id}")
            except Exception as e:
                logger.warning(f"Failed to extract cover art for book {book_id}: {e}")

        self.db.commit()
        self.db.refresh(book)

        logger.info(f"Confirmed match: {filename} → Book {book_id} ({book.title})")
        return book

    def import_as_new(self, filename: str) -> Book:
        """
        Import an unmatched file as a new book entry.

        Args:
            filename: Name of file in unassigned directory

        Returns:
            Created Book model

        Raises:
            ValueError: If file not found
        """
        source_file = self.unassigned_path / filename
        if not source_file.exists():
            raise ValueError(f"File not found: {filename}")

        # Extract metadata
        try:
            metadata = self.metadata_service.read_metadata(source_file)
        except Exception as e:
            logger.warning(f"Failed to extract metadata from {filename}: {e}")
            metadata = {}

        # Use metadata or fallback to filename
        title = metadata.get("title") or source_file.stem
        author = metadata.get("author") or "Unknown"

        # Generate destination filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_title = self._sanitize_filename(title)
        file_format = source_file.suffix.lower()
        dest_filename = f"{timestamp}_{safe_title}{file_format}"

        # Handle duplicates
        dest_path = settings.audiobooks_path / dest_filename
        counter = 1
        while dest_path.exists():
            dest_filename = f"{timestamp}_{safe_title}_{counter}{file_format}"
            dest_path = settings.audiobooks_path / dest_filename
            counter += 1

        # Move file
        shutil.move(str(source_file), str(dest_path))
        logger.info(f"Moved {filename} to {dest_path}")

        # Extract cover art
        cover_image_path = None
        try:
            timestamp_cover = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            cover_filename = f"{timestamp_cover}_{safe_title}.jpg"
            cover_dest_path = settings.covers_path / cover_filename

            if self.metadata_service.extract_cover_art(dest_path, cover_dest_path):
                cover_image_path = f"covers/{cover_filename}"
        except Exception as e:
            logger.warning(f"Failed to extract cover art: {e}")

        # Create book record
        book = Book(
            source=BookSource.IMPORTED,
            file_path=str(dest_path.relative_to(settings.audiobooks_path.parent)),
            file_size=dest_path.stat().st_size,
            file_format=file_format.lstrip("."),
            title=title,
            subtitle=metadata.get("subtitle"),
            author=author,
            narrator=metadata.get("narrator"),
            series=metadata.get("series"),
            series_position=metadata.get("series_position"),
            description=metadata.get("description"),
            publisher=metadata.get("publisher"),
            duration_seconds=metadata.get("duration_seconds"),
            cover_image_path=cover_image_path,
            genres=metadata.get("genres"),
            metadata_source=MetadataSource.FILE,
            downloaded_at=datetime.utcnow(),
        )

        self.db.add(book)
        self.db.commit()
        self.db.refresh(book)

        logger.info(f"Imported new book: {book.title} (ID: {book.id})")
        return book

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename by removing invalid characters.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        # Remove invalid filesystem characters
        safe = "".join(
            c for c in filename if c.isalnum() or c in (" ", "-", "_", ".")
        ).rstrip()

        # Limit length
        if len(safe) > 100:
            safe = safe[:100]

        return safe or "untitled"
