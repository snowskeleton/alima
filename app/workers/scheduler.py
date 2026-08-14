"""Background task scheduler using APScheduler."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..config import settings
from ..database import SessionLocal

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


def quick_sync_all_libraries():
    """Periodic task to quick sync all Audible libraries (checks for new books only)."""
    from ..services.audible_sync import AudibleSyncService
    from ..models import AudibleAccount

    logger.debug("Starting scheduled quick sync")
    db = SessionLocal()
    try:
        sync_service = AudibleSyncService(db)
        accounts = db.query(AudibleAccount).filter(AudibleAccount.enabled == True).all()

        overall_stats = {
            "accounts_synced": 0,
            "accounts_failed": 0,
            "total_books": 0,
            "new_books": 0,
            "updated_books": 0,
            "queued_downloads": 0,
            "covers_queued": 0,
        }

        for account in accounts:
            try:
                stats = sync_service.quick_sync_account(account)
                overall_stats["accounts_synced"] += 1
                overall_stats["total_books"] += stats["total"]
                overall_stats["new_books"] += stats["new"]
                overall_stats["updated_books"] += stats["updated"]
                overall_stats["queued_downloads"] += stats["queued"]
                overall_stats["covers_queued"] += stats["covers_queued"]
            except Exception as e:
                logger.error(f"Failed to quick sync account {account.username}: {e}")
                overall_stats["accounts_failed"] += 1

        # Only log at INFO if there was actual activity
        if overall_stats["new_books"] > 0 or overall_stats["updated_books"] > 0:
            from ..main import format_dict_pretty
            logger.info(f"Scheduled quick sync completed:{format_dict_pretty(overall_stats)}")
        else:
            logger.debug(f"Scheduled quick sync completed: no new or updated books")
    except Exception as e:
        logger.error(f"Error in scheduled quick sync: {e}", exc_info=True)
    finally:
        db.close()


def sync_all_libraries():
    """Periodic task to fully sync all Audible libraries (full library refresh)."""
    from ..services.audible_sync import AudibleSyncService

    logger.debug("Starting scheduled full library sync")
    db = SessionLocal()
    try:
        sync_service = AudibleSyncService(db)
        stats = sync_service.sync_all_accounts()
        # Full sync is always significant, log at INFO with formatted stats
        from ..main import format_dict_pretty
        logger.info(f"Scheduled full sync completed:{format_dict_pretty(stats)}")
    except Exception as e:
        logger.error(f"Error in scheduled full sync: {e}", exc_info=True)
    finally:
        db.close()


def process_download_queue():
    """Periodic task to process the download queue."""
    from ..services.book_download import BookDownloadService

    logger.debug("Starting scheduled download processing")
    db = SessionLocal()
    try:
        download_service = BookDownloadService(db)
        # Process all pending downloads with parallel execution
        # max_concurrent is controlled by settings
        stats = download_service.process_queue()
        # Only log at INFO if there was actual activity
        if stats["attempted"] > 0:
            from ..main import format_dict_pretty
            logger.info(f"Scheduled download processing completed:{format_dict_pretty(stats)}")
        else:
            logger.debug("Scheduled download processing completed: no downloads in queue")
    except Exception as e:
        logger.error(f"Error in scheduled download processing: {e}", exc_info=True)
    finally:
        db.close()


def reap_stale_downloads():
    """Periodic task to unstick downloads left in DOWNLOADING/DECRYPTING."""
    from ..services.book_download import BookDownloadService

    logger.debug("Starting scheduled stale download sweep")
    db = SessionLocal()
    try:
        stats = BookDownloadService(db).reap_stale_entries()
        if stats["requeued"] or stats["failed"]:
            logger.info(
                f"Stale download sweep: checked {stats['checked']}, "
                f"re-queued {stats['requeued']}, failed {stats['failed']}"
            )
        else:
            logger.debug(f"Stale download sweep: {stats['checked']} in flight, none stale")
    except Exception as e:
        logger.error(f"Error in stale download sweep: {e}", exc_info=True)
    finally:
        db.close()


def recover_interrupted_downloads():
    """
    Reclaim every in-flight download at startup, regardless of age.

    Download workers are threads in this process; none of them survive a
    restart, so anything still marked DOWNLOADING or DECRYPTING when we come
    up is abandoned by definition and would otherwise sit there forever.
    """
    from ..services.book_download import BookDownloadService

    db = SessionLocal()
    try:
        stats = BookDownloadService(db).reap_stale_entries(ignore_age=True)
        if stats["requeued"] or stats["failed"]:
            logger.info(
                f"Recovered {stats['requeued'] + stats['failed']} download(s) "
                f"interrupted by restart (re-queued {stats['requeued']}, "
                f"failed {stats['failed']})"
            )
    except Exception as e:
        logger.error(f"Error recovering interrupted downloads: {e}", exc_info=True)
    finally:
        db.close()


def process_b2_uploads():
    """Periodic task to upload downloaded books to Backblaze B2."""
    from ..services.b2_upload import B2UploadService
    from ..services.storage import get_storage_service

    if not get_storage_service():
        return

    logger.debug("Starting scheduled B2 upload sweep")
    db = SessionLocal()
    try:
        stats = B2UploadService(db).process_pending()
        if stats["attempted"] > 0:
            from ..main import format_dict_pretty
            logger.info(f"Scheduled B2 upload completed:{format_dict_pretty(stats)}")
        else:
            logger.debug("Scheduled B2 upload completed: nothing pending")
    except Exception as e:
        logger.error(f"Error in scheduled B2 upload: {e}", exc_info=True)
    finally:
        db.close()


def reconcile_b2_keys():
    """Periodic task to drop b2 keys whose objects have vanished from the bucket."""
    from ..services.b2_upload import B2UploadService
    from ..services.storage import get_storage_service

    if not get_storage_service():
        return

    logger.debug("Starting scheduled B2 key reconciliation")
    db = SessionLocal()
    try:
        stats = B2UploadService(db).reconcile_keys()
        if stats["cleared"] or stats["errors"]:
            logger.info(
                f"B2 reconciliation: checked {stats['checked']}, "
                f"cleared {stats['cleared']}, errors {stats['errors']}"
            )
        else:
            logger.debug(f"B2 reconciliation: all {stats['checked']} keys present")
    except Exception as e:
        logger.error(f"Error in scheduled B2 reconciliation: {e}", exc_info=True)
    finally:
        db.close()


def start_scheduler():
    """Start the background scheduler."""
    if scheduler.running:
        logger.warning("Scheduler is already running")
        return

    # Get sync intervals from database settings (with hardcoded defaults)
    from ..utils.settings_cache import get_cached_setting

    quick_sync_interval_minutes = get_cached_setting("quick_sync_interval_minutes", 1, int)
    full_sync_interval_minutes = get_cached_setting("full_sync_interval_minutes", 1440, int)
    b2_reconcile_interval_hours = get_cached_setting("b2_reconcile_interval_hours", 6, int)

    # Add quick sync job (runs frequently to check for new books)
    scheduler.add_job(
        quick_sync_all_libraries,
        trigger=IntervalTrigger(minutes=quick_sync_interval_minutes),
        id="quick_sync_libraries",
        name="Quick sync Audible libraries (new books only)",
        replace_existing=True,
    )
    logger.info(f"Scheduled quick sync to run every {quick_sync_interval_minutes} minutes")

    # Add full library sync job (runs less frequently for complete refresh)
    scheduler.add_job(
        sync_all_libraries,
        trigger=IntervalTrigger(minutes=full_sync_interval_minutes),
        id="full_sync_libraries",
        name="Full sync all Audible libraries",
        replace_existing=True,
    )
    logger.info(f"Scheduled full sync to run every {full_sync_interval_minutes} minutes ({full_sync_interval_minutes / 60:.1f} hours)")

    # Add download queue processing job (runs every 30 seconds for active processing)
    scheduler.add_job(
        process_download_queue,
        trigger=IntervalTrigger(seconds=30),
        id="process_downloads",
        name="Process download queue",
        replace_existing=True,
    )
    logger.debug("Scheduled download processing to run every 30 seconds")

    # Sweep for downloads wedged in DOWNLOADING/DECRYPTING. process_queue()
    # reaps too, but only when it runs — this covers the case where the queue
    # is otherwise idle and nothing would trigger a reap.
    # Runs well inside the staleness threshold: sweeping on the same period
    # would double the worst-case time to notice a wedged download.
    scheduler.add_job(
        reap_stale_downloads,
        trigger=IntervalTrigger(minutes=1),
        id="reap_stale_downloads",
        name="Recover stuck downloads",
        replace_existing=True,
    )
    logger.debug("Scheduled stale download sweep to run every minute")

    # Add B2 upload sweep (no-op unless B2 is configured). Runs less often than
    # the download queue since uploads are large and not latency-sensitive.
    scheduler.add_job(
        process_b2_uploads,
        trigger=IntervalTrigger(minutes=2),
        id="process_b2_uploads",
        name="Upload downloaded books to Backblaze B2",
        replace_existing=True,
    )
    logger.debug("Scheduled B2 upload sweep to run every 2 minutes")

    # Verify stored B2 keys still resolve. Hourly, not minutely: it costs one
    # HEAD per key, and objects don't disappear on their own often enough to
    # justify hammering the bucket. The serving path self-heals on demand
    # anyway — this is the sweep that catches files nobody has requested yet.
    scheduler.add_job(
        reconcile_b2_keys,
        trigger=IntervalTrigger(hours=b2_reconcile_interval_hours),
        id="reconcile_b2_keys",
        name="Verify Backblaze B2 keys still exist",
        replace_existing=True,
    )
    logger.debug(
        f"Scheduled B2 key reconciliation to run every {b2_reconcile_interval_hours} hours"
    )

    # Start the scheduler
    scheduler.start()
    logger.info("Background scheduler started")


def stop_scheduler():
    """Stop the background scheduler."""
    if not scheduler.running:
        logger.warning("Scheduler is not running")
        return

    scheduler.shutdown()
    logger.info("Background scheduler stopped")
