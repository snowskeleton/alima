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

    logger.info("Starting scheduled quick sync")
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

        logger.info(f"Scheduled quick sync completed: {overall_stats}")
    except Exception as e:
        logger.error(f"Error in scheduled quick sync: {e}", exc_info=True)
    finally:
        db.close()


def sync_all_libraries():
    """Periodic task to fully sync all Audible libraries (full library refresh)."""
    from ..services.audible_sync import AudibleSyncService

    logger.info("Starting scheduled full library sync")
    db = SessionLocal()
    try:
        sync_service = AudibleSyncService(db)
        stats = sync_service.sync_all_accounts()
        logger.info(f"Scheduled full sync completed: {stats}")
    except Exception as e:
        logger.error(f"Error in scheduled full sync: {e}", exc_info=True)
    finally:
        db.close()


def process_download_queue():
    """Periodic task to process the download queue."""
    from ..services.book_download import BookDownloadService

    logger.info("Starting scheduled download processing")
    db = SessionLocal()
    try:
        download_service = BookDownloadService(db)
        # Process all pending downloads with parallel execution
        # max_concurrent is controlled by settings
        stats = download_service.process_queue()
        logger.info(f"Scheduled download processing completed: {stats}")
    except Exception as e:
        logger.error(f"Error in scheduled download processing: {e}", exc_info=True)
    finally:
        db.close()


def start_scheduler():
    """Start the background scheduler."""
    if scheduler.running:
        logger.warning("Scheduler is already running")
        return

    # Get sync intervals from database settings (with hardcoded defaults)
    quick_sync_interval_seconds = 60  # Default: 60 seconds
    full_sync_interval_hours = 24  # Default: 24 hours (daily)
    try:
        from ..services.settings_service import SettingsService
        db = SessionLocal()
        settings_service = SettingsService(db)

        # Quick sync interval (for checking new books)
        db_quick_interval = settings_service.get("quick_sync_interval_seconds")
        if db_quick_interval:
            quick_sync_interval_seconds = int(db_quick_interval)

        # Full sync interval (for complete library refresh)
        db_full_interval = settings_service.get("full_sync_interval_hours")
        if db_full_interval:
            full_sync_interval_hours = int(db_full_interval)

        db.close()
    except Exception as e:
        logger.warning(f"Failed to load sync intervals from database, using defaults: {e}")

    # Add quick sync job (runs frequently to check for new books)
    scheduler.add_job(
        quick_sync_all_libraries,
        trigger=IntervalTrigger(seconds=quick_sync_interval_seconds),
        id="quick_sync_libraries",
        name="Quick sync Audible libraries (new books only)",
        replace_existing=True,
    )
    logger.info(f"Scheduled quick sync to run every {quick_sync_interval_seconds} seconds")

    # Add full library sync job (runs less frequently for complete refresh)
    scheduler.add_job(
        sync_all_libraries,
        trigger=IntervalTrigger(hours=full_sync_interval_hours),
        id="full_sync_libraries",
        name="Full sync all Audible libraries",
        replace_existing=True,
    )
    logger.info(f"Scheduled full sync to run every {full_sync_interval_hours} hours")

    # Add download queue processing job (runs every 30 seconds for active processing)
    scheduler.add_job(
        process_download_queue,
        trigger=IntervalTrigger(seconds=30),
        id="process_downloads",
        name="Process download queue",
        replace_existing=True,
    )
    logger.info("Scheduled download processing to run every 30 seconds")

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
