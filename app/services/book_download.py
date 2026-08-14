"""Service for downloading and decrypting books from Audible."""

import inspect
import json
import logging
import datetime
import shutil
import threading
import time
# from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

import audible
import httpx
import snowcrypt.snowcrypt as snowcrypt
from audible.aescipher import decrypt_voucher_from_licenserequest
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import AudibleAccount, Book, DownloadQueue, DownloadStatus, DownloadType

logger = logging.getLogger(__name__)

# Statuses that mean "a worker is supposed to be holding this entry right now".
IN_FLIGHT_STATUSES = [
    DownloadStatus.DOWNLOADING,
    DownloadStatus.DECRYPTING,
]

# Statuses that block a book from being queued again.
ACTIVE_STATUSES = [DownloadStatus.PENDING] + IN_FLIGHT_STATUSES

# How long an in-flight entry may go without its byte count moving before we
# assume the worker that owned it is gone. This measures progress, not age, so
# it can be far tighter than a whole-transfer timeout: a slow book keeps
# reporting bytes and is never reaped, however long it takes overall. Five
# minutes of a completely motionless transfer is already well past anything a
# healthy download does, and failing fast beats waiting.
DEFAULT_STALE_DOWNLOAD_MINUTES = 5

# Streamed to disk in chunks; also how often the progress callback fires.
DOWNLOAD_CHUNK_BYTES = 1024 * 1024

# Applies to connect/read/write individually, not the whole transfer, so a
# large book is fine but a dead connection surfaces in minutes.
DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, read=120.0)

# Floor between progress writes. Chunks arrive far faster than this and every
# write is a DB commit the queue page then polls.
PROGRESS_WRITE_INTERVAL_SECONDS = 5

# How often the decrypt watchdog stats the output file for a size change.
# Only used when snowcrypt can't report progress itself.
DECRYPT_POLL_SECONDS = 5

# snowcrypt gained progress_callback after 0.1.3. Detect rather than pin, so
# this keeps working on either side of the upgrade.
_SNOWCRYPT_REPORTS_PROGRESS = "progress_callback" in inspect.signature(
    snowcrypt.decrypt_aaxc
).parameters


def _stale_download_minutes() -> int:
    from ..utils.settings_cache import get_cached_setting

    return get_cached_setting(
        "stale_download_minutes", DEFAULT_STALE_DOWNLOAD_MINUTES, int
    )


def _as_utc(value: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    """Coerce a naive DB timestamp to UTC-aware so it can be compared."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def _describe_bytes(value: Optional[int]) -> str:
    """Human-readable byte count for log lines and error messages."""
    if not value:
        return "0 bytes"
    if value < 1024 * 1024:
        return f"{value / 1024:.0f} KB"
    if value < 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024):.0f} MB"
    return f"{value / (1024 * 1024 * 1024):.2f} GB"


def entry_eta_seconds(entry: DownloadQueue) -> Optional[int]:
    """
    Rough seconds remaining for an in-flight entry, from the average rate so
    far. None when there isn't enough to compute one.

    Deliberately naive: a flat average over the whole phase, no smoothing. It
    answers "roughly how long?" and will be wrong whenever the rate changes,
    which is fine — it is not a promise, and the byte counter next to it is the
    honest signal.
    """
    if entry.status not in IN_FLIGHT_STATUSES:
        return None

    done = entry.bytes_downloaded
    total = entry.total_bytes
    started = _as_utc(entry.phase_started_at) or _as_utc(entry.started_at)
    if not done or not total or started is None or done >= total:
        return None

    elapsed = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
    # Under a few seconds the rate estimate is mostly noise.
    if elapsed < 5:
        return None

    rate = done / elapsed
    if rate <= 0:
        return None

    return int((total - done) / rate)


def entry_idle_for(entry: DownloadQueue) -> Optional[datetime.timedelta]:
    """
    How long since this entry last showed signs of life, or None if it never
    showed any (in flight with no started_at, which is inconsistent by
    definition and treated as stale).

    Liveness is progress_at when the worker has reported bytes, falling back to
    started_at for an entry that hasn't reported its first chunk yet.
    """
    last_seen = _as_utc(entry.progress_at) or _as_utc(entry.started_at)
    if last_seen is None:
        return None
    return datetime.datetime.now(datetime.timezone.utc) - last_seen


def is_entry_stale(entry: DownloadQueue, stale_minutes: Optional[int] = None) -> bool:
    """
    True if the entry claims to be in flight but hasn't moved a byte in a long
    time — the worker died, the process restarted, or a decrypt hung.

    Note this is *not* a duration cap. An entry that keeps reporting progress
    stays alive indefinitely; only a stalled one is reaped.
    """
    if entry.status not in IN_FLIGHT_STATUSES:
        return False

    if stale_minutes is None:
        stale_minutes = _stale_download_minutes()

    idle = entry_idle_for(entry)
    if idle is None:
        return True

    return idle > datetime.timedelta(minutes=stale_minutes)


class _ProgressReporter:
    """
    Persists "this entry is still moving" for an in-flight download.

    Writes go through a dedicated short-lived session rather than the worker's,
    so this is safe to call from the decrypt watchdog thread and can't disturb
    whatever transaction the worker has open. Writes are throttled: chunks
    arrive far more often than the queue page is polled, and every write is a
    commit.
    """

    def __init__(self, queue_entry_id: int):
        self.queue_entry_id = queue_entry_id
        self._last_written_at = 0.0
        self._last_value = -1

    def report(self, value: int, total: Optional[int] = None, force: bool = False) -> None:
        now = time.monotonic()
        if not force:
            if value == self._last_value:
                return
            if now - self._last_written_at < PROGRESS_WRITE_INTERVAL_SECONDS:
                return

        self._last_written_at = now
        self._last_value = value

        db = SessionLocal()
        try:
            values = {
                "bytes_downloaded": value,
                "progress_at": datetime.datetime.now(datetime.timezone.utc),
            }
            if total is not None:
                values["total_bytes"] = total
            db.query(DownloadQueue).filter(
                DownloadQueue.id == self.queue_entry_id
            ).update(values, synchronize_session=False)
            db.commit()
        except Exception as e:
            # Progress is advisory. Losing a heartbeat write is survivable;
            # failing the download over it is not.
            logger.debug(f"Could not record progress for queue {self.queue_entry_id}: {e}")
            db.rollback()
        finally:
            db.close()


class _DecryptWatchdog:
    """
    Reports decrypt progress by watching the output file grow.

    snowcrypt offers no progress callback and isn't ours to change, but it
    writes the decrypted stream incrementally, so the output file's size is an
    honest liveness signal. Runs as a daemon thread for the duration of the
    decrypt.
    """

    def __init__(self, queue_entry_id: int, output_path: Path):
        self.output_path = output_path
        self.reporter = _ProgressReporter(queue_entry_id)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(DECRYPT_POLL_SECONDS):
            try:
                size = self.output_path.stat().st_size
            except OSError:
                # Not created yet, or already moved. Either way, nothing to say.
                continue
            self.reporter.report(size)

    def __enter__(self) -> "_DecryptWatchdog":
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._stop.set()
        self._thread.join(timeout=DECRYPT_POLL_SECONDS + 1)


class BookDownloadService:
    """Service for downloading and decrypting audiobooks."""

    def __init__(self, db: Session):
        """Initialize download service."""
        self.db = db

    def reap_stale_entries(
        self, stale_minutes: Optional[int] = None, ignore_age: bool = False
    ) -> dict:
        """
        Recover downloads wedged in DOWNLOADING/DECRYPTING.

        Nothing outside a live worker ever moves an entry out of those two
        statuses, so an entry left in one is unrecoverable on its own: the
        queue processor only picks up PENDING, and the "already queued" check
        refuses to re-queue the book. This sweep is what unsticks them.

        Args:
            stale_minutes: Age threshold; defaults to the configured setting.
            ignore_age: Reap every in-flight entry regardless of age. Used at
                startup, where no worker can possibly still own one.

        Returns:
            Dictionary with reap statistics.
        """
        max_attempts = self._max_attempts()
        entries = (
            self.db.query(DownloadQueue)
            .filter(DownloadQueue.status.in_(IN_FLIGHT_STATUSES))
            .all()
        )

        stats = {"checked": len(entries), "requeued": 0, "failed": 0}

        for entry in entries:
            if not ignore_age and not is_entry_stale(entry, stale_minutes):
                continue

            idle = entry_idle_for(entry)
            idle_desc = (
                f"idle {int(idle.total_seconds() // 60)}m" if idle else "never reported progress"
            )
            got = _describe_bytes(entry.bytes_downloaded)
            was = entry.status.value

            # A process that died holding this entry never got to try, so it
            # shouldn't spend one of the book's attempts — otherwise a restart
            # loop burns through all of them in minutes and permanently fails a
            # book that was downloading fine. Refund it.
            if ignore_age and entry.attempts > 0:
                entry.attempts -= 1

            if entry.attempts < max_attempts:
                entry.status = DownloadStatus.PENDING
                entry.error_message = (
                    f"Recovered: {was} stalled at {got} ({idle_desc}), re-queued automatically"
                )
                entry.started_at = None
                entry.progress_at = None
                entry.phase_started_at = None
                entry.bytes_downloaded = None
                entry.total_bytes = None
                stats["requeued"] += 1
            else:
                entry.status = DownloadStatus.FAILED
                entry.error_message = (
                    f"Stalled in {was} at {got} ({idle_desc}) after {entry.attempts} attempts"
                )
                stats["failed"] += 1

            logger.warning(
                f"Reaped stale download entry {entry.id} ({entry.asin}): "
                f"{was} at {got}, {idle_desc} -> {entry.status.value}"
            )

        if stats["requeued"] or stats["failed"]:
            self.db.commit()

        return stats

    def _max_attempts(self) -> int:
        from ..utils.settings_cache import get_cached_setting

        return get_cached_setting("max_download_attempts", 3, int)

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

        # Unstick anything a dead worker left behind before looking for work,
        # so a wedged entry rejoins this same batch instead of waiting for the
        # next sweep.
        self.reap_stale_entries()

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
                logger.debug(f"Skipping book {queue_entry.book_id} - marked as download_unavailable")
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
                        logger.debug(f"Successfully completed download for {queue_entry.asin}")
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
        # Start from zero so a retry doesn't inherit the previous attempt's
        # byte count and look like it's already partway through.
        queue_entry.bytes_downloaded = 0
        queue_entry.total_bytes = None
        queue_entry.progress_at = queue_entry.started_at
        queue_entry.phase_started_at = queue_entry.started_at
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
            logger.debug(f"Requesting license for {queue_entry.asin} with quality: {download_quality}")
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

            logger.debug(f"Downloading encrypted .aaxc file for '{book.title}' ({queue_entry.asin})")
            # The license round-trip happens with the entry already marked
            # DOWNLOADING but before a single byte moves. On a slow day that
            # silence could outlast the staleness threshold and get a perfectly
            # healthy worker reaped, so mark the handover explicitly.
            # Time the transfer from here too, so the rate isn't diluted by
            # however long the license took.
            queue_entry.phase_started_at = datetime.datetime.now(datetime.timezone.utc)
            self.db.commit()

            progress = _ProgressReporter(queue_entry.id)
            progress.report(0, force=True)

            self._download_file(
                download_url, aaxc_file, client, progress_callback=progress.report
            )
            logger.debug(f"Downloaded encrypted file for '{book.title}' ({aaxc_file.stat().st_size} bytes)")

            # Get and save voucher
            voucher_dict = decrypt_voucher_from_licenserequest(auth, license_response)
            with open(voucher_file, "w") as f:
                json.dump(voucher_dict, f, indent=2)

            # Decrypt to .m4a
            logger.debug(f"Starting decryption for '{book.title}' ({queue_entry.asin})")
            queue_entry.status = DownloadStatus.DECRYPTING
            # Restart the counter: from here it measures bytes decrypted, and
            # the transition itself is a fresh sign of life.
            queue_entry.bytes_downloaded = 0
            queue_entry.total_bytes = aaxc_file.stat().st_size
            queue_entry.progress_at = datetime.datetime.now(datetime.timezone.utc)
            queue_entry.phase_started_at = queue_entry.progress_at
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

            logger.debug(f"Decrypting {queue_entry.asin} to temporary location: {temp_output_file}")

            # Decrypt using snowcrypt to temp location, reporting progress so a
            # long decrypt reads as alive rather than stalled.
            self._decrypt_with_progress(
                queue_entry,
                aaxc_file,
                temp_output_file,
                voucher_dict["key"],
                voucher_dict["iv"],
            )
            logger.debug(f"Successfully decrypted '{book.title}' ({temp_output_file.stat().st_size} bytes)")

            # Determine final output location
            output_dir = settings.audiobooks_path
            output_dir.mkdir(parents=True, exist_ok=True)
            final_filename = f"{safe_title}.m4a"
            final_output_file = output_dir / final_filename

            # Handle duplicate filenames in the final location. A name is taken
            # if a file is already there OR if another book has reserved it in
            # the database but hasn't moved its file across yet.
            counter = 1
            while final_output_file.exists() or self._path_reserved(final_output_file, book.id):
                final_filename = f"{safe_title}_{counter}.m4a"
                final_output_file = output_dir / final_filename
                counter += 1

            decrypted_size = temp_output_file.stat().st_size
            relative_path = str(final_output_file.relative_to(settings.audiobooks_path.parent))

            # Reserve the path in the database BEFORE the file lands in the
            # audiobooks directory.
            #
            # The sync's file-integrity check scans that directory every minute
            # and treats any file it can't match to a book row as orphaned —
            # moving it to unassigned/. If we moved first and committed after,
            # a scan landing in that window would find a file no row claims,
            # relocate it, and leave this book pointing at a path that no
            # longer exists. Committing first means the scan always sees the
            # claim, whichever order the two processes interleave in.
            book.file_path = relative_path
            book.file_size = decrypted_size
            book.file_format = "m4a"
            book.downloaded_at = datetime.datetime.now(datetime.timezone.utc)
            self.db.commit()

            # Move completed file from temp to its reserved final location.
            logger.debug(f"Moving decrypted file to final location: {final_output_file}")
            try:
                shutil.move(str(temp_output_file), str(final_output_file))
            except Exception:
                # Release the reservation so the book isn't left claiming a
                # file that never arrived.
                book.file_path = None
                book.file_size = None
                book.file_format = None
                book.downloaded_at = None
                self.db.commit()
                raise

            # B2 upload is NOT done here on purpose — a multi-hundred-MB upload
            # would hold this download worker for its whole duration and stall
            # the queue. The scheduled B2 upload sweep picks this book up on its
            # next pass (see services/b2_upload.py).

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

            # Log completion with metrics
            speed_mb_s = (queue_entry.download_speed_kbps / 1024) if queue_entry.download_speed_kbps else 0
            size_mb = (book.file_size / 1024 / 1024) if book.file_size else 0
            logger.info(
                f"Successfully completed download for '{book.title}' ({queue_entry.asin}): "
                f"{size_mb:.1f} MB in {queue_entry.duration_seconds}s at {speed_mb_s:.1f} MB/s"
            )

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
        # Start from zero so a retry doesn't inherit the previous attempt's
        # byte count and look like it's already partway through.
        queue_entry.bytes_downloaded = 0
        queue_entry.total_bytes = None
        queue_entry.progress_at = queue_entry.started_at
        queue_entry.phase_started_at = queue_entry.started_at
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
            # (B2 upload happens in the scheduled sweep — see services/b2_upload.py)
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

    def _decrypt_with_progress(
        self,
        queue_entry: DownloadQueue,
        aaxc_file: Path,
        output_file: Path,
        key: str,
        iv: str,
    ) -> None:
        """
        Decrypt, reporting bytes written as it goes.

        Prefers snowcrypt's own progress callback, which reports exactly what
        it has written. Older snowcrypt releases don't have it, so fall back to
        a watchdog thread that watches the output file grow — a coarser signal,
        but enough to tell moving from wedged.
        """
        progress = _ProgressReporter(queue_entry.id)

        if _SNOWCRYPT_REPORTS_PROGRESS:
            snowcrypt.decrypt_aaxc(
                str(aaxc_file),
                str(output_file),
                key,
                iv,
                progress_callback=lambda written, total: progress.report(written, total),
            )
            return

        logger.debug(
            "snowcrypt has no progress_callback; falling back to output-size watchdog"
        )
        with _DecryptWatchdog(queue_entry.id, output_file):
            snowcrypt.decrypt_aaxc(str(aaxc_file), str(output_file), key, iv)

    def _download_file(
        self,
        url: str,
        output_path: Path,
        audible_client=None,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    ) -> None:
        """
        Stream a file from URL to local path.

        The body is streamed to disk a chunk at a time rather than buffered:
        an audiobook is routinely over a gigabyte, and holding one (let alone
        two concurrently) in memory is what got workers OOM-killed.

        Args:
            url: URL to download from
            output_path: Local path to save file
            audible_client: Optional audible.Client instance for authenticated downloads
            progress_callback: Called with (bytes_written, total_bytes_or_None)
                as the transfer advances. Total comes from Content-Length and
                is None when the server doesn't send one.
        """
        logger.debug(f"Downloading from {url[:80]}...")

        # CloudFront URLs are pre-signed and require the Audible app User-Agent header
        # Without this header, CloudFront WAF blocks the request with 403
        is_cloudfront = "cloudfront.net" in url.lower()

        if audible_client and not is_cloudfront:
            # Use authenticated client for non-CloudFront Audible API URLs.
            # stream=True returns a context manager wrapping httpx's own
            # stream(), with the auth flow and cookies already applied.
            stream_ctx = audible_client.raw_request(
                "GET",
                url,
                stream=True,
                apply_cookies=True,
                apply_auth_flow=True,
                follow_redirects=True,
                timeout=DOWNLOAD_TIMEOUT,
            )
        elif is_cloudfront:
            # Use plain httpx with Audible User-Agent for CloudFront CDN
            headers = {
                "User-Agent": "Audible/671 CFNetwork/1240.0.4 Darwin/20.6.0"
            }
            stream_ctx = httpx.stream(
                "GET", url, headers=headers, follow_redirects=True,
                timeout=DOWNLOAD_TIMEOUT,
            )
        else:
            # Fallback for unauthenticated downloads
            stream_ctx = httpx.stream(
                "GET", url, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT,
            )

        with stream_ctx as response:
            if response.status_code != 200:
                # The body hasn't been read yet on a streamed response.
                response.read()
                logger.error(f"Download failed with status {response.status_code}")
                logger.error(f"Response body: {response.text[:500]}")
                response.raise_for_status()

            total = response.headers.get("Content-Length")
            total_bytes = int(total) if total and total.isdigit() else None

            written = 0
            with open(output_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=DOWNLOAD_CHUNK_BYTES):
                    f.write(chunk)
                    written += len(chunk)
                    if progress_callback:
                        progress_callback(written, total_bytes)

            # A short body is not always an error to httpx — a connection that
            # closes at a chunk boundary can end the iteration quietly. Left
            # unchecked, the truncated .aaxc goes on to the decrypter, which
            # fails deep inside a CBC block with a message about padding that
            # says nothing about the real cause. Fail here, where it's obvious
            # and the entry can simply be retried.
            #
            # Compare raw bytes off the wire, not what we wrote: with a
            # Content-Encoding the header describes the encoded length while
            # iter_bytes() yields decoded bytes, and the two legitimately
            # differ.
            received = getattr(response, "num_bytes_downloaded", written)
            if total_bytes is not None and received != total_bytes:
                raise IOError(
                    f"Truncated download: got {received} of {total_bytes} bytes "
                    f"({_describe_bytes(received)} of {_describe_bytes(total_bytes)})"
                )

        logger.debug(f"Downloaded {written} bytes to {output_path}")

    def _path_reserved(self, output_path: Path, exclude_book_id: int) -> bool:
        """True if another book already claims this path in the database."""
        relative_path = str(output_path.relative_to(settings.audiobooks_path.parent))
        return (
            self.db.query(Book)
            .filter(Book.file_path == relative_path, Book.id != exclude_book_id)
            .first()
            is not None
        )

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

    def download_book_now(self, book_id: int, force: bool = False) -> dict:
        """
        Queue a book for immediate download (non-blocking).

        Args:
            book_id: ID of the book to download
            force: Re-queue even if an entry is already in flight. Without it,
                an entry that is genuinely stuck (its worker died mid-download
                or mid-decrypt) is still re-queued automatically once it passes
                the staleness threshold — force only skips the wait.

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
                DownloadQueue.status.in_(ACTIVE_STATUSES),
            )
            .order_by(DownloadQueue.created_at.desc())
            .first()
        )

        if existing_queue:
            # An entry sitting in DOWNLOADING/DECRYPTING with no live worker
            # behind it would otherwise block this book forever: the queue
            # processor ignores it and this check refuses to add another.
            # Reclaim it instead of reporting a download that isn't happening.
            if force or is_entry_stale(existing_queue):
                was = existing_queue.status.value
                existing_queue.status = DownloadStatus.PENDING
                existing_queue.error_message = None
                existing_queue.attempts = 0
                existing_queue.started_at = None
                existing_queue.priority = max(existing_queue.priority, 999)
                self.db.commit()

                reason = "forced" if force else f"stuck in {was}"
                logger.info(
                    f"Re-queued book {book.asin} ({reason}, queue_id: {existing_queue.id})"
                )
                return {
                    "success": True,
                    "message": f"Book '{book.title}' was {reason} and has been re-queued",
                    "queue_id": existing_queue.id,
                    "status": DownloadStatus.PENDING.value,
                    "requeued": True,
                }

            # Genuinely in flight or waiting its turn.
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
