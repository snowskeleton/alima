"""Service for syncing library from Audible API."""

import logging
import shutil
import time
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
from ..utils.html_text import html_to_text

logger = logging.getLogger(__name__)

# How recently a file in the audiobooks directory can have been written before
# the integrity check will call it orphaned and move it to unassigned/.
ORPHAN_GRACE_SECONDS = 600


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
        logger.debug(f"Starting quick sync for account: {account.username}")

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
                logger.debug(f"Fetching books purchased after {purchased_after}")

            # Fetch library from Audible
            library = client.get("1.0/library", params=params)

            if library is None:
                raise ValueError("Failed to fetch library from Audible API")

            items = library.get("items") or []
            # Only log at INFO if we actually found something
            if items:
                logger.info(f"Found {len(items)} new/updated books in library")
            else:
                logger.debug("Found 0 new/updated books in library")

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
            logger.debug("Verifying file integrity for all books...")
            integrity_stats = self._verify_file_integrity()
            stats["files_verified"] = integrity_stats["verified"]
            stats["files_missing"] = integrity_stats["missing"]
            stats["files_fixed"] = integrity_stats["fixed"]
            stats["orphaned_files"] = integrity_stats["orphaned_files"]
            stats["reconnected"] = integrity_stats["reconnected"]
            stats["moved_to_unassigned"] = integrity_stats["moved_to_unassigned"]

            # Only log completion at INFO if there was actual activity
            if stats["new"] > 0 or stats["updated"] > 0 or stats["files_fixed"] > 0 or stats["reconnected"] > 0:
                from ..main import format_dict_pretty
                logger.info(f"Quick sync complete for {account.username}:{format_dict_pretty(stats)}")
            else:
                logger.debug(f"Quick sync complete for {account.username}: no changes")

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
            logger.debug("Verifying file integrity for all books...")
            integrity_stats = self._verify_file_integrity()
            stats["files_verified"] = integrity_stats["verified"]
            stats["files_missing"] = integrity_stats["missing"]
            stats["files_fixed"] = integrity_stats["fixed"]
            stats["orphaned_files"] = integrity_stats["orphaned_files"]
            stats["reconnected"] = integrity_stats["reconnected"]
            stats["moved_to_unassigned"] = integrity_stats["moved_to_unassigned"]

            # Full sync always logs at INFO (it's a significant operation)
            from ..main import format_dict_pretty
            logger.info(f"Full sync complete for {account.username}:{format_dict_pretty(stats)}")

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

    def force_refresh_all_metadata(self, account: AudibleAccount = None) -> dict:
        """
        Force refresh metadata for all books from Audible API.
        This will update ALL fields including purchased_at, even if already set.

        Args:
            account: Optional specific account to refresh. If None, refreshes all accounts.

        Returns:
            Dictionary with refresh statistics
        """
        logger.info("Starting force metadata refresh for all books")

        stats = {
            "accounts_processed": 0,
            "books_updated": 0,
            "books_unchanged": 0,
            "errors": 0,
        }

        try:
            # Get accounts to process
            if account:
                accounts = [account]
            else:
                accounts = self.db.query(AudibleAccount).filter(AudibleAccount.enabled == True).all()

            for acc in accounts:
                logger.info(f"Force refreshing metadata for account: {acc.username}")
                stats["accounts_processed"] += 1

                # Load authenticator
                auth_file = settings.audible_auth_path / acc.auth_file_path
                if not auth_file.exists():
                    logger.error(f"Auth file not found: {auth_file}")
                    stats["errors"] += 1
                    continue

                auth = audible.Authenticator.from_file(str(auth_file))
                client = audible.Client(auth)

                # Fetch entire library (no purchased_after filter)
                params = {
                    "response_groups": "contributors, media, product_desc, series, product_extended_attrs, product_attrs",
                    "num_results": 999,
                    "page": 1,
                }

                library = client.get("1.0/library", params=params)
                if not library or "items" not in library:
                    logger.error(f"Failed to fetch library for {acc.username}")
                    stats["errors"] += 1
                    continue

                items = library.get("items", [])
                logger.info(f"Fetched {len(items)} books from Audible for {acc.username}")

                # Update each book with force_update=True
                for item in items:
                    asin = item.get("asin")
                    if not asin:
                        continue

                    # Find existing book
                    existing_book = (
                        self.db.query(Book)
                        .filter(Book.asin == asin, Book.audible_account_id == acc.id)
                        .first()
                    )

                    if existing_book:
                        # Force update metadata
                        if self._update_book_metadata(existing_book, item, acc, force_update=True):
                            stats["books_updated"] += 1
                        else:
                            stats["books_unchanged"] += 1

                self.db.commit()

            from ..main import format_dict_pretty
            logger.info(f"Force metadata refresh complete:{format_dict_pretty(stats)}")
            return stats

        except Exception as e:
            logger.error(f"Error during force metadata refresh: {e}", exc_info=True)
            self.db.rollback()
            stats["errors"] += 1
            raise

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
        # publisher_summary is an HTML fragment; the UI renders descriptions as
        # plain text, so flatten it to match imported books.
        description = html_to_text(item.get("publisher_summary"))
        publisher = item.get("publisher_name")

        # Parse release date
        publish_date = None
        release_date_str = item.get("release_date")
        if release_date_str:
            try:
                publish_date = datetime.fromisoformat(release_date_str.replace("Z", "+00:00"))
            except Exception:
                pass

        # Parse purchase date
        purchased_at = None
        purchase_date_str = item.get("purchase_date")
        if purchase_date_str:
            try:
                purchased_at = datetime.fromisoformat(purchase_date_str.replace("Z", "+00:00"))
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
            purchased_at=purchased_at,
            duration_seconds=duration_seconds,
            cover_url=cover_url,
            genres=genres_list if genres_list else None,
            metadata_source=MetadataSource.AUDIBLE,
            synced_from_master=False,
        )

        return book

    def _update_book_metadata(
        self, book: Book, item: dict, account: AudibleAccount, force_update: bool = False
    ) -> bool:
        """
        Update book metadata from Audible API item.

        Args:
            book: Existing Book model
            item: Book data from Audible API
            account: AudibleAccount this book belongs to
            force_update: If True, update all fields even if already set

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

        # Update purchase date if not already set (or if force_update is True)
        if not book.purchased_at or force_update:
            purchase_date_str = item.get("purchase_date")
            if purchase_date_str:
                try:
                    purchased_at = datetime.fromisoformat(purchase_date_str.replace("Z", "+00:00"))
                    if book.purchased_at != purchased_at:
                        book.purchased_at = purchased_at
                        updated = True
                except Exception:
                    pass

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
        Verify file integrity in both directions:
        1. Books marked as downloaded actually have files on disk
        2. Files on disk are properly associated with books in database

        Returns:
            Dictionary with verification statistics
        """
        from .book_download import IN_FLIGHT_STATUSES

        stats = {
            "verified": 0,
            "missing": 0,
            "fixed": 0,
            "orphaned_files": 0,
            "reconnected": 0,
            "moved_to_unassigned": 0,
            "skipped_in_flight": 0,
        }

        # Books a download worker is actively writing. Their file may be
        # mid-move between the temp directory and its reserved final path, so
        # neither half of this check can draw conclusions about them yet.
        in_flight_book_ids = {
            row[0]
            for row in self.db.query(DownloadQueue.book_id)
            .filter(DownloadQueue.status.in_(IN_FLIGHT_STATUSES))
            .all()
        }

        # PART 1: Check books that claim to have files
        logger.debug("Checking books marked as downloaded...")
        books_with_files = self.db.query(Book).filter(Book.file_path.isnot(None)).all()

        for book in books_with_files:
            if book.id in in_flight_book_ids:
                stats["skipped_in_flight"] += 1
                continue

            stats["verified"] += 1

            # Build absolute path to file
            file_path = Path(book.file_path)
            if not file_path.is_absolute():
                file_path = settings.audiobooks_path.parent / book.file_path

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

        # PART 2: Check for orphaned files (files that exist but aren't in database)
        logger.debug("Checking for orphaned files in audiobooks directory...")

        # Get all books without files for matching
        books_without_files = self.db.query(Book).filter(Book.file_path.is_(None)).all()

        # Scan audiobooks directory for files
        supported_formats = [".m4a", ".m4b", ".mp3"]

        if settings.audiobooks_path.exists():
            for file_path in settings.audiobooks_path.iterdir():
                # Skip directories (like 'unassigned')
                if not file_path.is_file():
                    continue

                # Skip unsupported formats
                if file_path.suffix.lower() not in supported_formats:
                    continue

                # Check if this file is already associated with a book
                relative_path = str(file_path.relative_to(settings.audiobooks_path.parent))
                existing_book = self.db.query(Book).filter(Book.file_path == relative_path).first()

                if existing_book:
                    # File is already properly associated
                    continue

                # A file that appeared moments ago is far more likely to be a
                # download still settling than a genuine orphan. Relocating it
                # to unassigned/ would break the download that just wrote it,
                # so leave anything this recent for the next pass.
                try:
                    age_seconds = time.time() - file_path.stat().st_mtime
                except OSError:
                    # Vanished between listing and stat — nothing to judge.
                    continue

                if age_seconds < ORPHAN_GRACE_SECONDS:
                    logger.debug(
                        f"Skipping recently written file '{file_path.name}' "
                        f"({int(age_seconds)}s old) — may still be in flight"
                    )
                    stats["skipped_in_flight"] += 1
                    continue

                # This is an orphaned file - try to find its book
                stats["orphaned_files"] += 1
                logger.info(f"Found orphaned file: {file_path.name}")

                # Try to match by ASIN (for Audible books)
                matched_book = None

                # First, try extracting ASIN from file metadata (most reliable)
                try:
                    from .metadata import MetadataService
                    metadata_service = MetadataService()
                    file_metadata = metadata_service.read_metadata(file_path)

                    if file_metadata and file_metadata.get("asin"):
                        asin = file_metadata["asin"]
                        matched_book = self.db.query(Book).filter(
                            Book.asin == asin,
                            Book.file_path.is_(None)
                        ).first()
                        if matched_book:
                            logger.info(f"Matched file to book by metadata ASIN ({asin}): {matched_book.title}")
                except Exception as e:
                    logger.debug(f"Could not extract ASIN from metadata for {file_path.name}: {e}")

                # Fallback: Extract potential ASIN from filename (ASINs are alphanumeric, typically 10 chars)
                if not matched_book:
                    filename_parts = file_path.stem.split('_')
                    for part in filename_parts:
                        if len(part) == 10 and part.isalnum():
                            # This might be an ASIN
                            potential_asin = part
                            matched_book = self.db.query(Book).filter(
                                Book.asin == potential_asin,
                                Book.file_path.is_(None)
                            ).first()
                            if matched_book:
                                logger.info(f"Matched file to book by filename ASIN ({potential_asin}): {matched_book.title}")
                                break

                # If no ASIN match, try to extract metadata and fuzzy match
                if not matched_book and books_without_files:
                    try:
                        from .metadata import MetadataService
                        metadata_service = MetadataService()
                        file_metadata = metadata_service.read_metadata(file_path)

                        # Try to match by title
                        if file_metadata and file_metadata.get("title"):
                            file_title = file_metadata["title"].lower()

                            from rapidfuzz import fuzz
                            best_score = 0
                            best_match = None

                            for book in books_without_files:
                                if book.title:
                                    score = fuzz.ratio(file_title, book.title.lower())
                                    if score > best_score:
                                        best_score = score
                                        best_match = book

                            # Use high threshold (95%) to avoid incorrect matches
                            if best_match and best_score >= 95:
                                matched_book = best_match
                                logger.info(f"Matched file to book by title (score {best_score}): {matched_book.title}")
                    except Exception as e:
                        logger.warning(f"Failed to extract metadata from {file_path.name}: {e}")

                # If we found a match, associate the file with the book
                if matched_book:
                    matched_book.file_path = relative_path
                    matched_book.file_size = file_path.stat().st_size
                    matched_book.file_format = file_path.suffix.lower().lstrip(".")
                    matched_book.downloaded_at = datetime.utcnow()

                    stats["reconnected"] += 1
                    logger.info(f"Reconnected file '{file_path.name}' to book '{matched_book.title}'")

                    # Remove from books_without_files list to avoid duplicate matching
                    books_without_files = [b for b in books_without_files if b.id != matched_book.id]
                else:
                    # No match found - move to unassigned directory for manual matching
                    try:
                        unassigned_dir = settings.audiobooks_path / "unassigned"
                        unassigned_dir.mkdir(parents=True, exist_ok=True)
                        dest_path = unassigned_dir / file_path.name

                        # Handle filename conflicts
                        counter = 1
                        while dest_path.exists():
                            stem = file_path.stem
                            suffix = file_path.suffix
                            dest_path = unassigned_dir / f"{stem}_{counter}{suffix}"
                            counter += 1

                        shutil.move(str(file_path), str(dest_path))
                        stats["moved_to_unassigned"] += 1
                        logger.info(f"Moved unmatched file '{file_path.name}' to unassigned directory")

                        # Send email notification about the file needing matching
                        try:
                            import asyncio
                            from .email_service import EmailService

                            # Run the async email notification
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    asyncio.create_task(EmailService.send_matching_notification(
                                        filename=dest_path.name,
                                        file_path=str(dest_path)
                                    ))
                                else:
                                    asyncio.run(EmailService.send_matching_notification(
                                        filename=dest_path.name,
                                        file_path=str(dest_path)
                                    ))
                            except RuntimeError:
                                # No event loop, create one
                                asyncio.run(EmailService.send_matching_notification(
                                    filename=dest_path.name,
                                    file_path=str(dest_path)
                                ))
                        except Exception as email_error:
                            # Don't fail the sync if email fails
                            logger.warning(f"Failed to send matching notification email: {email_error}")

                    except Exception as e:
                        logger.error(f"Failed to move unmatched file '{file_path.name}': {e}")

        # Commit all changes and log results if there was activity
        if stats["fixed"] > 0 or stats["reconnected"] > 0 or stats["moved_to_unassigned"] > 0:
            self.db.commit()
            from ..main import format_dict_pretty
            logger.info(f"File integrity check found issues:{format_dict_pretty(stats)}")
        else:
            logger.debug("File integrity check complete: no issues found")

        return stats
