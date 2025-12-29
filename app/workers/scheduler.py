"""Background task scheduler using APScheduler."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..config import settings
from ..database import SessionLocal

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


def sync_all_libraries():
    """Periodic task to sync all Audible libraries."""
    from ..services.audible_sync import AudibleSyncService

    logger.info("Starting scheduled library sync")
    db = SessionLocal()
    try:
        sync_service = AudibleSyncService(db)
        stats = sync_service.sync_all_accounts()
        logger.info(f"Scheduled sync completed: {stats}")
    except Exception as e:
        logger.error(f"Error in scheduled sync: {e}", exc_info=True)
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

    # Get sync interval from database settings (with hardcoded default)
    sync_interval_hours = 6  # Default: 6 hours
    try:
        from ..services.settings_service import SettingsService
        db = SessionLocal()
        settings_service = SettingsService(db)
        db_interval = settings_service.get("sync_interval_hours")
        if db_interval:
            sync_interval_hours = int(db_interval)
        db.close()
    except Exception as e:
        logger.warning(f"Failed to load sync interval from database, using default: {e}")

    # Add library sync job (runs every N hours based on settings)
    scheduler.add_job(
        sync_all_libraries,
        trigger=IntervalTrigger(hours=sync_interval_hours),
        id="sync_libraries",
        name="Sync all Audible libraries",
        replace_existing=True,
    )
    logger.info(f"Scheduled library sync to run every {sync_interval_hours} hours")

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
