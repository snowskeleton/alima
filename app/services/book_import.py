"""Service for importing third-party audiobooks."""

import logging
import shutil
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Book, BookSource, MetadataSource
from .metadata import MetadataService

logger = logging.getLogger(__name__)


class BookImportService:
    """Service for importing third-party audiobooks."""

    def __init__(self, db: Session):
        """Initialize the import service."""
        self.db = db
        self.metadata_service = MetadataService()

    def import_book(
        self,
        source_file_path: Path,
        title: Optional[str] = None,
        author: Optional[str] = None,
        extract_metadata: bool = True,
    ) -> Book:
        """
        Import a third-party audiobook file.

        Args:
            source_file_path: Path to the source audio file
            title: Optional title override
            author: Optional author override
            extract_metadata: Whether to extract metadata from file

        Returns:
            Created Book model

        Raises:
            ValueError: If file is not valid or cannot be imported
        """
        # Validate file exists
        if not source_file_path.exists():
            raise ValueError(f"File not found: {source_file_path}")

        # Validate file format
        valid_formats = [".m4a", ".m4b", ".mp3"]
        file_format = source_file_path.suffix.lower()
        if file_format not in valid_formats:
            raise ValueError(
                f"Unsupported file format: {file_format}. "
                f"Supported formats: {', '.join(valid_formats)}"
            )

        # Extract metadata from file if requested
        metadata = {}
        if extract_metadata:
            metadata = self.metadata_service.read_metadata(source_file_path)
            logger.info(f"Extracted metadata: {metadata}")

        # Use provided title/author or fall back to extracted metadata
        final_title = title or metadata.get("title") or source_file_path.stem
        final_author = author or metadata.get("author") or "Unknown"

        # Generate clean filename (sanitize title)
        safe_title = "".join(
            c for c in final_title if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        filename = f"{safe_title}{file_format}"

        # Copy file to audiobooks directory
        dest_path = settings.audiobooks_path / filename
        settings.audiobooks_path.mkdir(parents=True, exist_ok=True)

        # Handle duplicate filenames
        counter = 1
        while dest_path.exists():
            filename = f"{safe_title}_{counter}{file_format}"
            dest_path = settings.audiobooks_path / filename
            counter += 1

        shutil.copy2(source_file_path, dest_path)

        logger.info(f"Copied file to {dest_path}")

        # Get file size
        file_size = dest_path.stat().st_size

        # Extract cover art if present
        cover_image_path = None
        if extract_metadata:
            cover_filename = f"{safe_title}.jpg"
            cover_dest_path = settings.covers_path / cover_filename

            # Handle duplicate cover filenames
            counter = 1
            while cover_dest_path.exists():
                cover_filename = f"{safe_title}_{counter}.jpg"
                cover_dest_path = settings.covers_path / cover_filename
                counter += 1

            if self.metadata_service.extract_cover_art(dest_path, cover_dest_path):
                cover_image_path = f"covers/{cover_filename}"

        # Create book record
        book = Book(
            source=BookSource.IMPORTED,
            file_path=str(dest_path.relative_to(settings.audiobooks_path.parent)),
            file_size=file_size,
            file_format=file_format.lstrip("."),
            title=final_title,
            subtitle=metadata.get("subtitle"),
            author=final_author,
            narrator=metadata.get("narrator"),
            series=metadata.get("series"),
            series_position=metadata.get("series_position"),
            description=metadata.get("description"),
            publisher=metadata.get("publisher"),
            duration_seconds=metadata.get("duration_seconds"),
            cover_image_path=cover_image_path,
            genres=metadata.get("genres"),
            metadata_source=MetadataSource.FILE,
        )

        self.db.add(book)
        self.db.commit()
        self.db.refresh(book)

        logger.info(f"Imported book: {book.title} (ID: {book.id})")

        return book

    def import_book_with_metadata(
        self,
        source_file_path: Path,
        metadata: dict,
    ) -> Book:
        """
        Import a book with manually provided metadata.

        Args:
            source_file_path: Path to the source audio file
            metadata: Dictionary of metadata fields

        Returns:
            Created Book model
        """
        # Validate file
        if not source_file_path.exists():
            raise ValueError(f"File not found: {source_file_path}")

        file_format = source_file_path.suffix.lower()
        valid_formats = [".m4a", ".m4b", ".mp3"]
        if file_format not in valid_formats:
            raise ValueError(f"Unsupported file format: {file_format}")

        # Generate clean filename (sanitize title)
        title = metadata.get("title", source_file_path.stem)
        safe_title = "".join(
            c for c in title if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        filename = f"{safe_title}{file_format}"

        # Copy file to audiobooks directory
        dest_path = settings.audiobooks_path / filename
        settings.audiobooks_path.mkdir(parents=True, exist_ok=True)

        # Handle duplicate filenames
        counter = 1
        while dest_path.exists():
            filename = f"{safe_title}_{counter}{file_format}"
            dest_path = settings.audiobooks_path / filename
            counter += 1

        shutil.copy2(source_file_path, dest_path)

        # Get file size
        file_size = dest_path.stat().st_size

        # Read duration from file if not provided
        duration_seconds = metadata.get("duration_seconds")
        if not duration_seconds:
            file_metadata = self.metadata_service.read_metadata(dest_path)
            duration_seconds = file_metadata.get("duration_seconds")

        # Create book record
        book = Book(
            source=BookSource.IMPORTED,
            file_path=str(dest_path.relative_to(settings.audiobooks_path.parent)),
            file_size=file_size,
            file_format=file_format.lstrip("."),
            title=metadata.get("title", "Unknown"),
            subtitle=metadata.get("subtitle"),
            author=metadata.get("author", "Unknown"),
            narrator=metadata.get("narrator"),
            series=metadata.get("series"),
            series_position=metadata.get("series_position"),
            description=metadata.get("description"),
            publisher=metadata.get("publisher"),
            duration_seconds=duration_seconds,
            cover_image_path=metadata.get("cover_image_path"),
            genres=metadata.get("genres"),
            metadata_source=MetadataSource.MANUAL,
        )

        self.db.add(book)
        self.db.commit()
        self.db.refresh(book)

        logger.info(f"Imported book with manual metadata: {book.title} (ID: {book.id})")

        return book
