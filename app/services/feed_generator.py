"""Service for generating RSS feeds."""

import logging
from datetime import datetime
from typing import List
from xml.etree.ElementTree import Element, SubElement, tostring

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Book, Feed, FeedType

logger = logging.getLogger(__name__)


class FeedGeneratorService:
    """Service for generating podcast RSS feeds."""

    def __init__(self, db: Session):
        """Initialize the feed generator."""
        self.db = db

    def generate_rss(self, feed: Feed) -> str:
        """
        Generate RSS XML for a feed.

        Args:
            feed: Feed model instance

        Returns:
            RSS XML as string
        """
        # Get books for this feed
        books = self._get_feed_books(feed)

        # Get domain from database settings
        from ..services.settings_service import SettingsService
        domain = SettingsService.get_domain(self.db)

        # Create RSS root element
        rss = Element("rss", version="2.0")
        rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
        rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")

        # Create channel element
        channel = SubElement(rss, "channel")

        # Channel metadata
        SubElement(channel, "title").text = feed.name
        SubElement(channel, "link").text = f"{domain}/feed/{feed.slug}"
        SubElement(channel, "description").text = feed.description or feed.name
        SubElement(channel, "language").text = "en-us"

        # Add lastBuildDate so consumers can see when feed was generated
        from datetime import datetime, timezone
        build_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        SubElement(channel, "lastBuildDate").text = build_date

        # Add pubDate based on most recent book (if any)
        if books:
            most_recent_book = books[0]
            pub_date_source = most_recent_book.purchased_at if most_recent_book.purchased_at else most_recent_book.added_at
            channel_pub_date = pub_date_source.strftime("%a, %d %b %Y %H:%M:%S +0000")
            SubElement(channel, "pubDate").text = channel_pub_date

        # iTunes-specific tags
        SubElement(channel, "itunes:author").text = settings.app_name
        SubElement(channel, "itunes:summary").text = feed.description or feed.name
        SubElement(channel, "itunes:explicit").text = "no"

        # Feed cover art
        cover_url = self._get_feed_cover_url(feed, domain)
        if cover_url:
            SubElement(channel, "itunes:image", href=cover_url)

        # Add items for each book
        for book in books:
            self._add_item(channel, book, feed, domain)

        # Convert to string
        xml_string = tostring(rss, encoding="utf-8", method="xml")
        return b'<?xml version="1.0" encoding="UTF-8"?>\n' + xml_string

    def _get_feed_books(self, feed: Feed) -> List[Book]:
        """
        Get books for a feed based on its type and criteria.

        Only includes books that have been downloaded (file_path exists).

        Args:
            feed: Feed model instance

        Returns:
            List of Book models
        """
        if feed.feed_type == FeedType.MANUAL:
            # For manual feeds, get books from FeedBooks association
            # Sort by position, filter out non-downloaded books
            return [
                fb.book
                for fb in sorted(feed.feed_books, key=lambda fb: fb.position)
                if fb.book.file_path is not None
            ]

        elif feed.feed_type == FeedType.SMART:
            # For smart feeds, apply filter criteria
            # Only include books with file_path (downloaded books)
            query = self.db.query(Book).filter(Book.file_path.isnot(None))

            if feed.filter_criteria:
                filters = self._normalize_filters(feed.filter_criteria)
                for f in filters:
                    condition = self._build_filter_condition(f)
                    if condition is not None:
                        query = query.filter(condition)

            # Order by added date, newest first
            query = query.order_by(Book.added_at.desc())

            return query.all()

        return []

    @staticmethod
    def _normalize_filters(filter_criteria: dict) -> list:
        """Convert filter_criteria to a list of filter dicts, handling legacy format."""
        if "filters" in filter_criteria:
            return filter_criteria["filters"]
        # Legacy format: {"type": "author", "value": "X"} -> single contains filter
        if "type" in filter_criteria and "value" in filter_criteria:
            return [{"field": filter_criteria["type"], "operator": "contains", "value": filter_criteria["value"]}]
        return []

    @staticmethod
    def _build_filter_condition(f: dict):
        """Build a SQLAlchemy filter condition from a filter dict."""
        field_name = f.get("field")
        operator = f.get("operator", "contains")
        value = f.get("value", "")

        valid_fields = {"title", "author", "series", "narrator", "publisher"}
        if field_name not in valid_fields:
            return None

        column = getattr(Book, field_name)

        if operator == "contains":
            return column.ilike(f"%{value}%")
        elif operator == "not_contains":
            return ~column.ilike(f"%{value}%")
        elif operator == "is":
            return func.lower(column) == value.lower()
        elif operator == "is_not":
            return func.lower(column) != value.lower()

        return None

    def _get_feed_cover_url(self, feed: Feed, domain: str) -> str:
        """
        Get cover image URL for a feed with priority fallback.

        Priority:
        1. Feed's custom cover_image_path
        2. Default feed cover URL from settings
        3. None

        Args:
            feed: Feed model instance
            domain: Domain URL to use for building URLs

        Returns:
            Cover image URL or None
        """
        # Priority 1: Feed's custom cover
        if feed.cover_image_path:
            return f"{domain}/files/{feed.cover_image_path}"

        # Priority 2: Default cover from settings
        from ..services.settings_service import SettingsService

        try:
            settings_service = SettingsService(self.db)
            default_cover_path = settings_service.get("default_feed_cover_url")
            if default_cover_path:
                return f"{domain}/files/{default_cover_path}"
        except Exception as e:
            logger.warning(f"Failed to get default feed cover URL from settings: {e}")

        # Priority 3: No cover
        return None

    def _add_item(self, channel: Element, book: Book, feed: Feed, domain: str) -> None:
        """
        Add an RSS item for a book.

        Args:
            channel: Channel XML element
            book: Book model instance
            feed: Feed model instance
            domain: Domain URL to use for building URLs
        """
        item = SubElement(channel, "item")

        # Format title with series info
        title = book.title

        # Remove " (Unabridged)" but keep " (Abridged)" if present
        # Note: Audible includes a space before the parenthesis
        if title.endswith(" (Unabridged)"):
            title = title[:-14].strip()
        elif title.endswith("(Unabridged)"):
            # Fallback for titles without the space
            title = title[:-13].strip()

        # Clean series name
        series_name = book.series
        if series_name:
            # Also remove (Unabridged) from series
            if series_name.endswith(" (Unabridged)"):
                series_name = series_name[:-14].strip()
            elif series_name.endswith("(Unabridged)"):
                series_name = series_name[:-13].strip()

            # Check if series is actually different from title (ignore case and minor differences)
            # Some files incorrectly have series set to title
            title_normalized = title.lower().strip().rstrip('!.?')
            series_normalized = series_name.lower().strip().rstrip('!.?')

            # Only add series info if it's meaningfully different from the title
            if series_normalized and series_normalized != title_normalized:
                series_text = series_name
                if book.series_position:
                    series_text += f", Book {book.series_position}"

                # Only add if not already in the title
                if series_text not in title:
                    title = f"{title}: {series_text}"

        SubElement(item, "title").text = title
        SubElement(item, "link").text = f"{domain}/library/{book.id}"

        # Description
        description = book.description or f"{book.title} by {book.author}"
        SubElement(item, "description").text = description

        # Author in itunes:subtitle tag
        if book.author:
            SubElement(item, "itunes:author").text = book.author
            SubElement(item, "itunes:subtitle").text = book.author

        # Duration (if available)
        if book.duration_seconds:
            hours = book.duration_seconds // 3600
            minutes = (book.duration_seconds % 3600) // 60
            seconds = book.duration_seconds % 60
            duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            SubElement(item, "itunes:duration").text = duration_str

        # Publication date - use purchased_at if available, else added_at
        pub_date_source = book.purchased_at if book.purchased_at else book.added_at
        pub_date = pub_date_source.strftime("%a, %d %b %Y %H:%M:%S +0000")
        SubElement(item, "pubDate").text = pub_date

        # GUID (unique identifier)
        guid = SubElement(item, "guid", isPermaLink="false")
        guid.text = f"{domain}/library/{book.id}"

        # Enclosure (audio file)
        # Use actual file format from book, fallback to m4b
        file_format = book.file_format or "m4b"
        audio_url = f"{domain}/files/audiobooks/{book.id}.{file_format}"

        # Determine media type based on format
        media_types = {
            "m4a": "audio/mp4",
            "m4b": "audio/x-m4b",
            "mp3": "audio/mpeg",
        }
        media_type = media_types.get(file_format.lower(), "audio/x-m4b")

        enclosure = SubElement(
            item,
            "enclosure",
            url=audio_url,
            length=str(book.file_size) if book.file_size else "0",
            type=media_type,
        )

        # Cover art
        if book.cover_image_path:
            image_url = f"{domain}/files/{book.cover_image_path}"
            SubElement(item, "itunes:image", href=image_url)
