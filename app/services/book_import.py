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
        narrator: Optional[str] = None,
        series: Optional[str] = None,
        series_position: Optional[str] = None,
        description: Optional[str] = None,
        publisher: Optional[str] = None,
        extract_metadata: bool = True,
    ) -> Book:
        """
        Import a third-party audiobook file.

        Extracts metadata and cover art from the audio file, then applies
        any provided values as overrides.

        Args:
            source_file_path: Path to the source audio file
            title: Optional title override
            author: Optional author override
            narrator: Optional narrator override
            series: Optional series override
            series_position: Optional series position override
            description: Optional description override
            publisher: Optional publisher override
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
        file_metadata = {}
        if extract_metadata:
            file_metadata = self.metadata_service.read_metadata(source_file_path)
            logger.info(f"Extracted metadata: {file_metadata}")

        # Provided values override extracted metadata
        final_title = title or file_metadata.get("title") or source_file_path.stem
        final_author = author or file_metadata.get("author") or "Unknown"

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

        # Determine metadata source
        has_overrides = any([title, author, narrator, series, series_position, description, publisher])
        metadata_source = MetadataSource.MANUAL if has_overrides else MetadataSource.FILE

        # Create book record
        book = Book(
            source=BookSource.IMPORTED,
            file_path=str(dest_path.relative_to(settings.audiobooks_path.parent)),
            file_size=file_size,
            file_format=file_format.lstrip("."),
            title=final_title,
            subtitle=file_metadata.get("subtitle"),
            author=final_author,
            narrator=narrator or file_metadata.get("narrator"),
            series=series or file_metadata.get("series"),
            series_position=series_position or file_metadata.get("series_position"),
            description=description or file_metadata.get("description"),
            publisher=publisher or file_metadata.get("publisher"),
            duration_seconds=file_metadata.get("duration_seconds"),
            cover_image_path=cover_image_path,
            genres=file_metadata.get("genres"),
            metadata_source=metadata_source,
        )

        self.db.add(book)
        self.db.commit()
        self.db.refresh(book)

        logger.info(f"Imported book: {book.title} (ID: {book.id})")

        return book
