"""Service for downloading and decrypting books from Audible."""

import json
import logging
import datetime
import shutil
# from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import audible
import httpx
import snowcrypt.snowcrypt as snowcrypt
from audible.aescipher import decrypt_voucher_from_licenserequest
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import AudibleAccount, Book, DownloadQueue, DownloadStatus, DownloadType

logger = logging.getLogger(__name__)


class BookDownloadService:
    """Service for downloading and decrypting audiobooks."""

    def __init__(self, db: Session):
        """Initialize download service."""
        self.db = db

    def process_queue(self, max_downloads: int = None, max_concurrent: int = None) -> dict:
        """
        Process pending downloads from the queue in parallel.

        Args:
            max_downloads: Maximum number of books to download in this batch (default: unlimited)
            max_concurrent: Maximum concurrent downloads (default: from config)

        Returns:
            Dictionary with download statistics
        """
        # Get max concurrent from database settings (with hardcoded default)
        if max_concurrent is None:
            from ..utils.settings_cache import get_cached_setting
            max_concurrent = get_cached_setting("max_concurrent_downloads", 3, int)

        # Get pending downloads ordered by priority (higher first)
        query = (
            self.db.query(DownloadQueue)
            .filter(DownloadQueue.status == DownloadStatus.PENDING)
            .order_by(DownloadQueue.priority.desc(), DownloadQueue.created_at)
        )

        if max_downloads:
            query = query.limit(max_downloads)

        pending = query.all()

        stats = {
            "attempted": len(pending),
            "completed": 0,
            "failed": 0,
        }

        if not pending:
            return stats

        # Only log at INFO if there are actually downloads to process
        logger.info(f"Processing {len(pending)} downloads from queue with {max_concurrent} concurrent workers")

        # Filter out books marked as unavailable
        valid_pending = []
        for queue_entry in pending:
            book = self.db.query(Book).filter(Book.id == queue_entry.book_id).first()
            if book and book.download_unavailable:
                logger.info(f"Skipping book {queue_entry.book_id} - marked as download_unavailable")
                # Remove from queue
                queue_entry.status = DownloadStatus.FAILED
                queue_entry.error_message = book.download_error_message or "Book unavailable for download"
                self.db.commit()
                stats["failed"] += 1
            else:
                valid_pending.append(queue_entry)

        if not valid_pending:
            return stats

        # Process downloads in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            # Submit all download tasks
            future_to_queue = {
                executor.submit(self._download_book_thread_safe, queue_entry.id): queue_entry
                for queue_entry in valid_pending
            }

            # Process completed downloads
            for future in as_completed(future_to_queue):
                queue_entry = future_to_queue[future]
                try:
                    result = future.result()
                    if result["success"]:
                        stats["completed"] += 1
                        logger.info(f"Successfully completed download for {queue_entry.asin}")
                    else:
                        stats["failed"] += 1
                        logger.error(f"Failed to download {queue_entry.asin}: {result.get('error')}")
                except Exception as e:
                    stats["failed"] += 1
                    logger.error(
                        f"Exception in download thread for {queue_entry.asin}: {e}",
                        exc_info=True,
                    )

        return stats

    def _download_book_thread_safe(self, queue_entry_id: int) -> dict:
        """
        Thread-safe wrapper for downloading a book or cover.
        Creates its own database session for thread safety.

        Args:
            queue_entry_id: ID of the DownloadQueue entry

        Returns:
            Dictionary with success status and optional error message
        """
        # Create a new database session for this thread
        db = SessionLocal()
        try:
            # Get the queue entry
            queue_entry = db.query(DownloadQueue).filter(DownloadQueue.id == queue_entry_id).first()
            if not queue_entry:
                return {"success": False, "error": "Queue entry not found"}

            # Create a temporary service instance with this thread's DB session
            temp_service = BookDownloadService(db)

            # Download based on type
            if queue_entry.download_type == DownloadType.COVER:
                temp_service._download_cover(queue_entry)
            else:
                temp_service._download_book(queue_entry)

            return {"success": True}

        except Exception as e:
            logger.error(f"Error in thread-safe download for queue {queue_entry_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            db.close()

    def _download_book(self, queue_entry: DownloadQueue) -> None:
        """
        Download and decrypt a single book.

        Args:
            queue_entry: DownloadQueue entry to process
        """
        # Update status
        queue_entry.status = DownloadStatus.DOWNLOADING
        queue_entry.started_at = datetime.datetime.now(datetime.timezone.utc)
        queue_entry.attempts += 1
        self.db.commit()

        try:
            # Get book and account
            book = (
                self.db.query(Book).filter(Book.id == queue_entry.book_id).first()
            )
            account = (
                self.db.query(AudibleAccount)
                .filter(AudibleAccount.id == queue_entry.audible_account_id)
                .first()
            )

            if not book or not account:
                raise Exception("Book or account not found")

            logger.info(
                f"Downloading book '{book.title}' (ASIN: {queue_entry.asin}) "
                f"from account '{account.username}'"
            )

            # Load authenticator
            auth_file = settings.audible_auth_path / account.auth_file_path
            auth = audible.Authenticator.from_file(str(auth_file))
            client = audible.Client(auth)

            logger.debug(f"Using auth file: {auth_file}")

            # Get download quality from database settings (with hardcoded default)
            from ..utils.settings_cache import get_cached_setting
            download_quality = get_cached_setting("download_quality", "High", str)

            # Request license
            logger.debug(f"Requesting license for {queue_entry.asin}")
            license_response = client.post(
                f"content/{queue_entry.asin}/licenserequest",
                body={
                    "drm_type": "Adrm",
                    "consumption_type": "Download",
                    "quality": download_quality,
                },
            )

            # Check if license was denied
            content_license = license_response.get("content_license", {})
            status_code = content_license.get("status_code")
            message = content_license.get("message")
            denial_reasons = content_license.get("license_denial_reasons", [])

            if status_code != "Granted":
                error_msg = f"License request denied (status: {status_code})"
                if message:
                    error_msg += f": {message}"
                if denial_reasons:
                    # Handle denial_reasons which could be a list of strings or dicts
                    reason_strs = []
                    for reason in denial_reasons:
                        if isinstance(reason, dict):
                            # Extract relevant fields from dict
                            reason_str = reason.get("message") or reason.get("type") or str(reason)
                            reason_strs.append(reason_str)
                        else:
                            reason_strs.append(str(reason))
                    error_msg += f" - Reasons: {', '.join(reason_strs)}"
                logger.error(error_msg)
                logger.error(f"Full denial_reasons: {denial_reasons}")

                # Mark book as unavailable for download
                book.download_unavailable = True
                book.download_error_message = error_msg
                self.db.commit()
                logger.info(f"Marked book {book.id} as download_unavailable")

                raise ValueError(error_msg)

            # Log the response structure for debugging
            logger.debug(f"License response keys: {license_response.keys()}")
            if "content_license" in license_response:
                logger.debug(f"Content license keys: {license_response['content_license'].keys()}")
                if "content_metadata" in license_response["content_license"]:
                    content_metadata = license_response["content_license"]["content_metadata"]
                    logger.debug(f"Content metadata keys: {content_metadata.keys() if content_metadata else 'EMPTY'}")

            # Get download URL - try different possible structures
            download_url = None
            content_metadata = license_response["content_license"]["content_metadata"]

            if not content_metadata:
                raise ValueError("License granted but no content metadata returned. This book may not be available for download.")

            try:
                # Try the standard structure first
                download_url = content_metadata["content_url"]["offline_url"]
            except KeyError:
                # Try alternative structure
                try:
                    if "content_reference" in content_metadata:
                        download_url = content_metadata["content_reference"]["content_url"]
                    elif "offline_url" in content_metadata:
                        download_url = content_metadata["offline_url"]
                    else:
                        # Log the full structure for debugging
                        logger.error(f"Unexpected license response structure. Content metadata: {content_metadata}")
                        raise ValueError("Could not find download URL in license response")
                except Exception as e:
                    logger.error(f"Failed to extract download URL from response: {e}")
                    raise

            logger.debug(f"Download URL: {download_url[:100]}...")

            # Download .aaxc file
            temp_dir = settings.temp_path
            temp_dir.mkdir(parents=True, exist_ok=True)

            aaxc_file = temp_dir / f"{queue_entry.asin}.aaxc"
            voucher_file = temp_dir / f"{queue_entry.asin}.voucher"

            logger.debug(f"Downloading .aaxc file for {queue_entry.asin}")
            # Use the client's raw_request method with apply_cookies=True
            # CloudFront URLs require website cookies, not just auth headers
            self._download_file(download_url, aaxc_file, client)

            # Get and save voucher
            voucher_dict = decrypt_voucher_from_licenserequest(auth, license_response)
            with open(voucher_file, "w") as f:
                json.dump(voucher_dict, f, indent=2)

            # Decrypt to .m4a
            queue_entry.status = DownloadStatus.DECRYPTING
            self.db.commit()

            # Create filename: sanitized title
            safe_title = self._sanitize_filename(book.title)
            filename = f"{safe_title}.m4a"

            # Decrypt to temp location first to avoid race condition with file integrity check
            # Use the existing temp directory where we downloaded the aaxc file
            temp_output_file = settings.temp_path / filename

            # Handle duplicate filenames in temp
            counter = 1
            while temp_output_file.exists():
                filename = f"{safe_title}_{counter}.m4a"
                temp_output_file = settings.temp_path / filename
                counter += 1

            logger.info(f"Decrypting {queue_entry.asin} to temporary location: {temp_output_file}")

            # Decrypt using snowcrypt to temp location
            snowcrypt.decrypt_aaxc(
                str(aaxc_file),
                str(temp_output_file),
                voucher_dict["key"],
                voucher_dict["iv"]
            )

            # Determine final output location
            output_dir = settings.audiobooks_path
            output_dir.mkdir(parents=True, exist_ok=True)
            final_filename = f"{safe_title}.m4a"
            final_output_file = output_dir / final_filename

            # Handle duplicate filenames in final location
            counter = 1
            while final_output_file.exists():
                final_filename = f"{safe_title}_{counter}.m4a"
                final_output_file = output_dir / final_filename
                counter += 1

            # Atomically move completed file from temp to final location
            # This prevents the integrity check from finding incomplete files
            logger.info(f"Moving decrypted file to final location: {final_output_file}")
            shutil.move(str(temp_output_file), str(final_output_file))

            # Update book record with final path
            book.file_path = str(final_output_file.relative_to(settings.audiobooks_path.parent))
            book.file_size = final_output_file.stat().st_size
            book.file_format = "m4a"
            book.downloaded_at = datetime.datetime.now(datetime.timezone.utc)

            # Commit immediately to prevent race condition with file integrity check
            # The file is now in the audiobooks directory, so the database must be updated ASAP
            self.db.commit()

            # Clean up temp files
            aaxc_file.unlink(missing_ok=True)
            voucher_file.unlink(missing_ok=True)

            # Mark as completed
            queue_entry.status = DownloadStatus.COMPLETED
            queue_entry.completed_at = datetime.datetime.now(datetime.timezone.utc)

            # Calculate download metrics
            queue_entry.file_size_bytes = book.file_size
            queue_entry.download_quality = download_quality
            if queue_entry.started_at and queue_entry.completed_at:
                # Ensure both datetimes are timezone-aware for subtraction
                start = queue_entry.started_at
                end = queue_entry.completed_at
                if start.tzinfo is None:
                    start = start.replace(tzinfo=datetime.timezone.utc)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=datetime.timezone.utc)

                duration = (end - start).total_seconds()
                queue_entry.duration_seconds = int(duration)
                if duration > 0 and book.file_size:
                    speed_kbps = (book.file_size / 1024) / duration
                    queue_entry.download_speed_kbps = int(speed_kbps)

            # Commit queue entry metrics
            self.db.commit()

            logger.info(f"Successfully downloaded and decrypted {queue_entry.asin}")

        except Exception as e:
            logger.error(f"Error downloading {queue_entry.asin}: {e}", exc_info=True)

            # Update queue entry with error
            queue_entry.status = DownloadStatus.FAILED
            queue_entry.error_message = str(e)[:500]  # Truncate long errors
            self.db.commit()

            raise

    def _download_cover(self, queue_entry: DownloadQueue) -> None:
        """
        Download cover image for a book.

        Args:
            queue_entry: DownloadQueue entry to process
        """
        # Update status
        queue_entry.status = DownloadStatus.DOWNLOADING
        queue_entry.started_at = datetime.datetime.now(datetime.timezone.utc)
        queue_entry.attempts += 1
        self.db.commit()

        try:
            # Get book and account
            book = (
                self.db.query(Book).filter(Book.id == queue_entry.book_id).first()
            )
            account = (
                self.db.query(AudibleAccount)
                .filter(AudibleAccount.id == queue_entry.audible_account_id)
                .first()
            )

            if not book or not account:
                raise Exception("Book or account not found")

            # Skip if book already has a cover
            if book.cover_image_path:
                logger.debug(f"Book '{book.title}' already has cover, skipping")
                queue_entry.status = DownloadStatus.COMPLETED
                queue_entry.completed_at = datetime.datetime.now(datetime.timezone.utc)
                self.db.commit()
                return

            logger.debug(f"Downloading cover for '{book.title}' (ASIN: {queue_entry.asin})")

            # Use the stored cover URL from database (set during sync)
            image_url = book.cover_url

            # If no URL stored, fetch it from Audible and update the book
            if not image_url:
                logger.info(f"No cover URL stored for {book.title}, fetching from Audible...")

                # Load authenticator and fetch library
                auth_file = settings.audible_auth_path / account.auth_file_path
                auth = audible.Authenticator.from_file(str(auth_file))
                client = audible.Client(auth)

                library = client.get(
                    "library",
                    params={
                        "response_groups": "contributors, media, product_desc, series, product_extended_attrs, product_attrs",
                        "num_results": 999,
                        "page": 1,
                    },
                )

                items = library.get("items") or []
                if not items:
                    raise ValueError(f"Book with ASIN {queue_entry.asin} not found in library")

                # Find the specific book by ASIN
                item = None
                for lib_item in items:
                    if lib_item.get("asin") == queue_entry.asin:
                        item = lib_item
                        break

                if not item:
                    raise ValueError(f"Book with ASIN {queue_entry.asin} not found in library")

                # Extract cover URL
                product_images = item.get("product_images")
                if product_images:
                    image_url = product_images.get("500") or next(iter(product_images.values()), None)

                if not image_url:
                    raise ValueError(f"No product images found for {book.title}")

                # Store the URL for future use
                book.cover_url = image_url
                self.db.commit()
                logger.debug(f"Stored cover URL for {book.title}")

            logger.debug(f"Cover URL: {image_url[:100]}...")

            # Ensure covers directory exists
            settings.covers_path.mkdir(parents=True, exist_ok=True)

            # Download image
            response = httpx.get(image_url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()

            # Determine file extension from content type
            content_type = response.headers.get("content-type", "")
            ext = ".jpg"  # Default to jpg
            if "png" in content_type:
                ext = ".png"
            elif "webp" in content_type:
                ext = ".webp"

            # Generate filename using ASIN
            cover_filename = f"{book.asin}{ext}"
            cover_path = settings.covers_path / cover_filename

            # Save image
            with open(cover_path, "wb") as f:
                f.write(response.content)

            # Update book record with relative path
            book.cover_image_path = f"covers/{cover_filename}"

            # Mark as completed
            queue_entry.status = DownloadStatus.COMPLETED
            queue_entry.completed_at = datetime.datetime.now(datetime.timezone.utc)

            # Calculate download metrics
            queue_entry.file_size_bytes = len(response.content)
            if queue_entry.started_at and queue_entry.completed_at:
                start = queue_entry.started_at
                end = queue_entry.completed_at
                if start.tzinfo is None:
                    start = start.replace(tzinfo=datetime.timezone.utc)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=datetime.timezone.utc)

                duration = (end - start).total_seconds()
                queue_entry.duration_seconds = int(duration)
                if duration > 0:
                    speed_kbps = (len(response.content) / 1024) / duration
                    queue_entry.download_speed_kbps = int(speed_kbps)

            self.db.commit()

            logger.info(f"Successfully downloaded cover for {book.title}: {cover_filename}")

        except Exception as e:
            logger.error(f"Error downloading cover for {queue_entry.asin}: {e}", exc_info=True)

            # Update queue entry with error
            queue_entry.status = DownloadStatus.FAILED
            queue_entry.error_message = str(e)[:500]  # Truncate long errors
            self.db.commit()

            raise

    def _download_file(self, url: str, output_path: Path, audible_client=None) -> None:
        """
        Download a file from URL to local path.

        Args:
            url: URL to download from
            output_path: Local path to save file
            audible_client: Optional audible.Client instance for authenticated downloads
        """
        logger.debug(f"Downloading from {url[:80]}...")

        # CloudFront URLs are pre-signed and require the Audible app User-Agent header
        # Without this header, CloudFront WAF blocks the request with 403
        is_cloudfront = "cloudfront.net" in url.lower()

        if audible_client and not is_cloudfront:
            # Use authenticated client for non-CloudFront Audible API URLs
            response = audible_client.raw_request(
                "GET",
                url,
                apply_cookies=True,
                apply_auth_flow=True,
                follow_redirects=True
            )
        elif is_cloudfront:
            # Use plain httpx with Audible User-Agent for CloudFront CDN
            headers = {
                "User-Agent": "Audible/671 CFNetwork/1240.0.4 Darwin/20.6.0"
            }
            response = httpx.get(url, headers=headers, follow_redirects=True)
        else:
            # Fallback for unauthenticated downloads
            response = httpx.get(url, follow_redirects=True)

        # Check response
        if response.status_code != 200:
            logger.error(f"Download failed with status {response.status_code}")
            logger.error(f"Response body: {response.text[:500]}")
            response.raise_for_status()

        # Save file
        file_size = len(response.content)
        logger.debug(f"Downloaded {file_size} bytes to {output_path}")
        with open(output_path, "wb") as f:
            f.write(response.content)

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for filesystem use.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename safe for filesystem
        """
        # Remove/replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")

        # Limit length
        max_length = 200
        if len(filename) > max_length:
            filename = filename[:max_length]

        return filename.strip()

    def download_book_now(self, book_id: int) -> dict:
        """
        Queue a book for immediate download (non-blocking).

        Args:
            book_id: ID of the book to download

        Returns:
            Dictionary with queue status and entry ID

        Raises:
            ValueError: If book is not found, already downloaded, or downloads are disabled
        """
        # Get book
        book = self.db.query(Book).filter(Book.id == book_id).first()
        if not book:
            raise ValueError(f"Book with ID {book_id} not found")

        # Check if already downloaded
        if book.file_path:
            raise ValueError(f"Book '{book.title}' is already downloaded")

        # Check if book has an ASIN (required for Audible downloads)
        if not book.asin or not book.audible_account_id:
            raise ValueError(f"Book '{book.title}' is not from Audible and cannot be downloaded")

        # Get audible account
        account = (
            self.db.query(AudibleAccount)
            .filter(AudibleAccount.id == book.audible_account_id)
            .first()
        )
        if not account:
            raise ValueError(f"Audible account not found for book '{book.title}'")

        # Check if already in queue
        existing_queue = (
            self.db.query(DownloadQueue)
            .filter(
                DownloadQueue.book_id == book_id,
                DownloadQueue.status.in_([DownloadStatus.PENDING, DownloadStatus.DOWNLOADING, DownloadStatus.DECRYPTING])
            )
            .first()
        )

        if existing_queue:
            # Already in queue
            logger.info(f"Book {book.asin} already in queue (queue_id: {existing_queue.id})")
            return {
                "success": True,
                "message": f"Book '{book.title}' is already queued for download",
                "queue_id": existing_queue.id,
                "status": existing_queue.status.value,
            }
        else:
            # Create new queue entry with high priority
            queue_entry = DownloadQueue(
                book_id=book_id,
                audible_account_id=book.audible_account_id,
                asin=book.asin,
                download_type=DownloadType.BOOK,
                priority=999,  # High priority for manual downloads
                status=DownloadStatus.PENDING,
                attempts=0,
            )
            self.db.add(queue_entry)
            self.db.commit()
            logger.info(f"Added book {book.asin} to queue (queue_id: {queue_entry.id})")

            return {
                "success": True,
                "message": f"Book '{book.title}' has been queued for download",
                "queue_id": queue_entry.id,
                "status": DownloadStatus.PENDING.value,
            }

    def retry_failed(self, max_attempts: int = 3) -> dict:
        """
        Retry failed downloads that haven't exceeded max attempts.

        Args:
            max_attempts: Maximum number of attempts before giving up

        Returns:
            Dictionary with retry statistics
        """
        failed = (
            self.db.query(DownloadQueue)
            .filter(
                DownloadQueue.status == DownloadStatus.FAILED,
                DownloadQueue.attempts < max_attempts,
            )
            .all()
        )

        logger.info(f"Retrying {len(failed)} failed downloads")

        stats = {"retried": 0, "completed": 0, "failed": 0}

        for queue_entry in failed:
            # Reset to pending for retry
            queue_entry.status = DownloadStatus.PENDING
            queue_entry.error_message = None
            stats["retried"] += 1

        self.db.commit()

        # Process the retries
        if stats["retried"] > 0:
            result = self.process_queue(max_downloads=len(failed))
            stats["completed"] = result["completed"]
            stats["failed"] = result["failed"]

        return stats
