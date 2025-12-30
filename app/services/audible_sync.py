"""Service for syncing library from Audible API."""

import logging
from datetime import datetime
from pathlib import Path

import audible
import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    AudibleAccount,
    Book,
    BookSource,
    DownloadQueue,
    DownloadStatus,
    DownloadType,
    MetadataSource,
)

logger = logging.getLogger(__name__)


class AudibleSyncService:
    """Service for syncing Audible library to database."""

    def __init__(self, db: Session):
        """Initialize sync service."""
        self.db = db

    def quick_sync_account(self, account: AudibleAccount) -> dict:
        """
        Quick sync library for a single Audible account using purchased_after.

        This method only fetches books purchased since the last sync,
        making it much faster than a full sync.

        Args:
            account: AudibleAccount to sync

        Returns:
            Dictionary with sync statistics
        """
        logger.info(f"Starting quick sync for account: {account.username}")

        try:
            # Load authenticator from file
            auth_file = settings.audible_auth_path / account.auth_file_path
            if not auth_file.exists():
                raise FileNotFoundError(f"Auth file not found: {auth_file}")

            auth = audible.Authenticator.from_file(str(auth_file))
            client = audible.Client(auth)

            # Build params for quick sync
            params = {
                "response_groups": "contributors, media, product_desc, series, product_extended_attrs, product_attrs",
                "num_results": 999,
                "page": 1,
            }

            # Add purchased_after filter if we have a last sync timestamp
            if account.last_sync_timestamp:
                # Format as RFC3339: 2025-01-01T00:00:00Z
                purchased_after = account.last_sync_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
                params["purchased_after"] = purchased_after
                logger.info(f"Fetching books purchased after {purchased_after}")

            # Fetch library from Audible
            library = client.get("1.0/library", params=params)

            if library is None:
                raise ValueError("Failed to fetch library from Audible API")

            items = library.get("items") or []
            logger.info(f"Found {len(items)} new/updated books in library")

            stats = {
                "total": len(items),
                "new": 0,
                "updated": 0,
                "queued": 0,
                "covers_queued": 0,
            }

            # Process items using the same logic as full sync
            for item in items:
                asin = item.get("asin")
                if not asin:
                    continue

                # Check if book already exists
                existing_book = (
                    self.db.query(Book).filter(Book.asin == asin).first()
                )

                if existing_book:
                    # Update metadata if changed
                    if self._update_book_metadata(existing_book, item, account):
                        stats["updated"] += 1
                    # Queue cover download if missing
                    if not existing_book.cover_image_path:
                        self._queue_cover_download(existing_book, account)
                        stats["covers_queued"] += 1
                else:
                    # Create new book entry
                    book = self._create_book_from_item(item, account)
                    self.db.add(book)
                    self.db.flush()  # Get book ID
                    # Queue cover download
                    self._queue_cover_download(book, account)
                    stats["new"] += 1
                    stats["covers_queued"] += 1

                    # Add to download queue if not already downloaded and downloads are enabled
                    if not book.file_path and account.downloads_enabled and book.download_enabled:
                        queue_entry = DownloadQueue(
                            book_id=book.id,
                            audible_account_id=account.id,
                            asin=asin,
                            download_type=DownloadType.BOOK,
                            priority=0,
                            status=DownloadStatus.PENDING,
                            attempts=0,
                        )
                        self.db.add(queue_entry)
                        stats["queued"] += 1

            # Update last sync timestamp
            account.last_sync_timestamp = datetime.utcnow()
            self.db.commit()

            # Verify file integrity for all books
            logger.info("Verifying file integrity for all books...")
            integrity_stats = self._verify_file_integrity()
            stats["files_verified"] = integrity_stats["verified"]
            stats["files_missing"] = integrity_stats["missing"]
            stats["files_fixed"] = integrity_stats["fixed"]

            logger.info(
                f"Quick sync complete for {account.username}: "
                f"{stats['new']} new, {stats['updated']} updated, "
                f"{stats['queued']} queued for download, "
                f"{stats['covers_queued']} covers queued, "
                f"{stats['files_verified']} files verified, "
                f"{stats['files_missing']} missing files detected and fixed"
            )

            return stats

        except Exception as e:
            logger.error(f"Error in quick sync for account {account.username}: {e}")
            self.db.rollback()
            raise

    def sync_account(self, account: AudibleAccount) -> dict:
        """
        Sync library for a single Audible account.

        Args:
            account: AudibleAccount to sync

        Returns:
            Dictionary with sync statistics
        """
        logger.info(f"Starting sync for account: {account.username}")

        try:
            # Load authenticator from file
            auth_file = settings.audible_auth_path / account.auth_file_path
            if not auth_file.exists():
                raise FileNotFoundError(f"Auth file not found: {auth_file}")

            auth = audible.Authenticator.from_file(str(auth_file))
            client = audible.Client(auth)

            # Fetch library from Audible
            library = client.get(
                "library",
                params={
                    "response_groups": "contributors, media, product_desc, series, product_extended_attrs, product_attrs",
                    "num_results": 999,
                    "page": 1,
                },
            )

            if library is None:
                raise ValueError("Failed to fetch library from Audible API")

            items = library.get("items") or []
            logger.info(f"Found {len(items)} books in library")

            stats = {
                "total": len(items),
                "new": 0,
                "updated": 0,
                "queued": 0,
                "covers_queued": 0,
            }

            for item in items:
                asin = item.get("asin")
                if not asin:
                    continue

                # Check if book already exists
                existing_book = (
                    self.db.query(Book).filter(Book.asin == asin).first()
                )

                if existing_book:
                    # Update metadata if changed
                    if self._update_book_metadata(existing_book, item, account):
                        stats["updated"] += 1
                    # Queue cover download if missing
                    if not existing_book.cover_image_path:
                        self._queue_cover_download(existing_book, account)
                        stats["covers_queued"] += 1
                else:
                    # Create new book entry
                    book = self._create_book_from_item(item, account)
                    self.db.add(book)
                    self.db.flush()  # Get book ID
                    # Queue cover download
                    self._queue_cover_download(book, account)
                    stats["new"] += 1
                    stats["covers_queued"] += 1

                    # Add to download queue if not already downloaded and downloads are enabled
                    # Check both account-level and book-level download flags
                    if not book.file_path and account.downloads_enabled and book.download_enabled:
                        queue_entry = DownloadQueue(
                            book_id=book.id,
                            audible_account_id=account.id,
                            asin=asin,
                            download_type=DownloadType.BOOK,
                            priority=0,
                            status=DownloadStatus.PENDING,
                            attempts=0,
                        )
                        self.db.add(queue_entry)
                        stats["queued"] += 1

            # Update last sync timestamp
            account.last_sync_timestamp = datetime.utcnow()
            self.db.commit()

            # Verify file integrity for all books
            logger.info("Verifying file integrity for all books...")
            integrity_stats = self._verify_file_integrity()
            stats["files_verified"] = integrity_stats["verified"]
            stats["files_missing"] = integrity_stats["missing"]
            stats["files_fixed"] = integrity_stats["fixed"]

            logger.info(
                f"Sync complete for {account.username}: "
                f"{stats['new']} new, {stats['updated']} updated, "
                f"{stats['queued']} queued for download, "
                f"{stats['files_verified']} files verified, "
                f"{stats['files_missing']} missing files detected and fixed"
            )

            return stats

        except Exception as e:
            logger.error(f"Error syncing account {account.username}: {e}")
            self.db.rollback()
            raise

    def sync_all_accounts(self) -> dict:
        """
        Sync library for all enabled Audible accounts.

        Returns:
            Dictionary with overall sync statistics
        """
        accounts = (
            self.db.query(AudibleAccount).filter(AudibleAccount.enabled == True).all()
        )

        logger.info(f"Syncing {len(accounts)} enabled accounts")

        overall_stats = {
            "accounts_synced": 0,
            "accounts_failed": 0,
            "total_books": 0,
            "new_books": 0,
            "updated_books": 0,
            "queued_downloads": 0,
        }

        for account in accounts:
            try:
                stats = self.sync_account(account)
                overall_stats["accounts_synced"] += 1
                overall_stats["total_books"] += stats["total"]
                overall_stats["new_books"] += stats["new"]
                overall_stats["updated_books"] += stats["updated"]
                overall_stats["queued_downloads"] += stats["queued"]
            except Exception as e:
                logger.error(f"Failed to sync account {account.username}: {e}")
                overall_stats["accounts_failed"] += 1

        return overall_stats

    def _create_book_from_item(
        self, item: dict, account: AudibleAccount
    ) -> Book:
        """
        Create a Book model from Audible API item.

        Args:
            item: Book data from Audible API
            account: AudibleAccount this book belongs to

        Returns:
            Book model instance
        """
        # Extract metadata
        title = item.get("title", "Unknown Title")
        subtitle = item.get("subtitle")

        # Authors
        authors = item.get("authors") or []
        author_str = ", ".join([a.get("name", "") for a in authors]) if authors else None

        # Narrators
        narrators = item.get("narrators") or []
        narrator_str = (
            ", ".join([n.get("name", "") for n in narrators]) if narrators else None
        )

        # Series
        series_info = item.get("series") or []
        series = None
        series_position = None
        if series_info:
            series = series_info[0].get("title")
            series_position = series_info[0].get("sequence")

        # Other metadata
        description = item.get("publisher_summary")
        publisher = item.get("publisher_name")

        # Parse release date
        publish_date = None
        release_date_str = item.get("release_date")
        if release_date_str:
            try:
                publish_date = datetime.fromisoformat(release_date_str.replace("Z", "+00:00"))
            except Exception:
                pass

        # Duration in seconds
        duration_seconds = item.get("runtime_length_min")
        if duration_seconds:
            duration_seconds = int(duration_seconds) * 60  # Convert minutes to seconds

        # Genres/categories
        genres_list = []
        category_ladders = item.get("category_ladders") or []
        for ladder in category_ladders:
            ladder_items = ladder.get("ladder") or []
            for cat in ladder_items:
                name = cat.get("name")
                if name and name not in genres_list:
                    genres_list.append(name)

        # Extract cover URL
        cover_url = None
        product_images = item.get("product_images")
        if product_images:
            # Try to get 500px image (standard size), fallback to any available
            cover_url = product_images.get("500") or next(iter(product_images.values()), None)

        book = Book(
            asin=item.get("asin"),
            audible_account_id=account.id,
            source=BookSource.AUDIBLE,
            title=title,
            subtitle=subtitle,
            author=author_str,
            narrator=narrator_str,
            series=series,
            series_position=series_position,
            description=description,
            publisher=publisher,
            publish_date=publish_date,
            duration_seconds=duration_seconds,
            cover_url=cover_url,
            genres=genres_list if genres_list else None,
            metadata_source=MetadataSource.AUDIBLE,
            synced_from_master=False,
        )

        return book

    def _update_book_metadata(
        self, book: Book, item: dict, account: AudibleAccount
    ) -> bool:
        """
        Update book metadata from Audible API item.

        Args:
            book: Existing Book model
            item: Book data from Audible API
            account: AudibleAccount this book belongs to

        Returns:
            True if book was updated, False otherwise
        """
        # Only update if metadata source is Audible and no manual overrides
        if book.metadata_source != MetadataSource.AUDIBLE or book.metadata_override:
            return False

        updated = False

        # Check if title changed
        new_title = item.get("title", "Unknown Title")
        if book.title != new_title:
            book.title = new_title
            updated = True

        # Update cover URL if available and different
        product_images = item.get("product_images")
        if product_images:
            new_cover_url = product_images.get("500") or next(iter(product_images.values()), None)
            if new_cover_url and book.cover_url != new_cover_url:
                book.cover_url = new_cover_url
                updated = True

        # Update last_metadata_update if changed
        if updated:
            book.last_metadata_update = datetime.utcnow()
            book.last_modified = datetime.utcnow()

        return updated

    def _queue_cover_download(self, book: Book, account: AudibleAccount) -> None:
        """
        Queue cover image for download.

        Args:
            book: Book model to download cover for
            account: AudibleAccount for this book
        """
        try:
            # Check if already queued
            existing_queue = (
                self.db.query(DownloadQueue)
                .filter(
                    DownloadQueue.book_id == book.id,
                    DownloadQueue.download_type == DownloadType.COVER,
                    DownloadQueue.status.in_([DownloadStatus.PENDING, DownloadStatus.DOWNLOADING])
                )
                .first()
            )

            if existing_queue:
                logger.debug(f"Cover for {book.title} already queued")
                return

            # Queue the cover download
            queue_entry = DownloadQueue(
                book_id=book.id,
                audible_account_id=account.id,
                asin=book.asin,
                download_type=DownloadType.COVER,
                priority=100,  # Higher priority than books for better UX
                status=DownloadStatus.PENDING,
                attempts=0,
            )
            self.db.add(queue_entry)
            logger.debug(f"Queued cover download for {book.title}")

        except Exception as e:
            logger.error(f"Failed to queue cover download for {book.title}: {e}")

    def _verify_file_integrity(self) -> dict:
        """
        Verify that all books marked as downloaded actually have files on disk.

        If a file is missing, clear the file-related fields and re-enable downloads.

        Returns:
            Dictionary with verification statistics
        """
        stats = {
            "verified": 0,
            "missing": 0,
            "fixed": 0,
        }

        # Get all books that claim to have a file
        books_with_files = self.db.query(Book).filter(Book.file_path.isnot(None)).all()

        for book in books_with_files:
            stats["verified"] += 1

            # Build absolute path to file
            file_path = Path(book.file_path)
            if not file_path.is_absolute():
                file_path = settings.audiobooks_path / file_path

            # Check if file exists
            if not file_path.exists():
                logger.warning(f"Missing file for book '{book.title}': {file_path}")
                stats["missing"] += 1

                # Clear file-related fields
                book.file_path = None
                book.file_size = None
                book.file_format = None
                book.downloaded_at = None

                # Re-enable downloads for Audible books
                if book.source == BookSource.AUDIBLE:
                    book.download_enabled = True
                    logger.info(f"Re-enabled downloads for '{book.title}'")

                stats["fixed"] += 1

        # Commit changes if any files were fixed
        if stats["fixed"] > 0:
            self.db.commit()
            logger.info(f"Fixed {stats['fixed']} books with missing files")

        return stats
