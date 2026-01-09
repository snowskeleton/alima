"""Routes for viewing logs and download statistics."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import require_admin
from ..models import DownloadQueue, DownloadStatus, DownloadType, User

router = APIRouter(prefix="/logs", tags=["Logs"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    view: str = Query("stats", description="View type: stats, downloads, raw"),
    days: int = Query(7, description="Number of days to show stats for"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Display logs page with different views.

    Views:
    - stats: Aggregated download statistics
    - downloads: Download queue history
    - raw: Raw log file contents
    """
    from ..utils.flash import get_flashed_messages

    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    context = {
        "request": request,
        "current_user": current_user,
        "messages": get_flashed_messages(request),
        "view": view,
        "days": days,
    }

    if view == "stats":
        # Get aggregated download statistics
        stats = _get_download_stats(db, start_date, end_date)
        context["stats"] = stats

    elif view == "downloads":
        # Get recent download entries
        downloads = (
            db.query(DownloadQueue)
            .filter(DownloadQueue.created_at >= start_date)
            .order_by(DownloadQueue.created_at.desc())
            .limit(1000)
            .all()
        )
        context["downloads"] = downloads

    elif view == "raw":
        # Get raw log file contents
        log_lines = _get_recent_log_lines(limit=1000)
        context["log_lines"] = log_lines

    return templates.TemplateResponse(
        request=request,
        name="admin/logs.html",
        context=context,
    )


@router.get("/raw", response_class=PlainTextResponse)
async def raw_logs(
    lines: int = Query(1000, description="Number of lines to return"),
    current_user: User = Depends(require_admin),
):
    """Get raw log file contents as plain text."""
    log_lines = _get_recent_log_lines(limit=lines)
    return "\n".join(log_lines)


def _get_download_stats(
    db: Session,
    start_date: datetime,
    end_date: datetime
) -> dict:
    """
    Calculate aggregated download statistics.

    Returns dictionary with:
    - total_downloads: Total number of downloads
    - successful_downloads: Number of completed downloads
    - failed_downloads: Number of failed downloads
    - pending_downloads: Number of pending downloads
    - total_data_downloaded: Total bytes downloaded
    - average_speed: Average download speed in KB/s
    - downloads_by_day: Daily download counts
    - top_quality: Most common quality setting
    """
    # Basic counts by status
    total_downloads = db.query(DownloadQueue).filter(
        DownloadQueue.created_at >= start_date,
        DownloadQueue.created_at <= end_date,
        DownloadQueue.download_type == DownloadType.BOOK,
    ).count()

    successful_downloads = db.query(DownloadQueue).filter(
        DownloadQueue.created_at >= start_date,
        DownloadQueue.created_at <= end_date,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
    ).count()

    failed_downloads = db.query(DownloadQueue).filter(
        DownloadQueue.created_at >= start_date,
        DownloadQueue.created_at <= end_date,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.FAILED,
    ).count()

    pending_downloads = db.query(DownloadQueue).filter(
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status.in_([DownloadStatus.PENDING, DownloadStatus.DOWNLOADING, DownloadStatus.DECRYPTING]),
    ).count()

    # Data volume stats
    total_data = db.query(
        func.sum(DownloadQueue.file_size_bytes)
    ).filter(
        DownloadQueue.created_at >= start_date,
        DownloadQueue.created_at <= end_date,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
        DownloadQueue.file_size_bytes.isnot(None),
    ).scalar() or 0

    # Speed stats
    avg_speed = db.query(
        func.avg(DownloadQueue.download_speed_kbps)
    ).filter(
        DownloadQueue.created_at >= start_date,
        DownloadQueue.created_at <= end_date,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
        DownloadQueue.download_speed_kbps.isnot(None),
    ).scalar() or 0

    # Duration stats
    avg_duration = db.query(
        func.avg(DownloadQueue.duration_seconds)
    ).filter(
        DownloadQueue.created_at >= start_date,
        DownloadQueue.created_at <= end_date,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
        DownloadQueue.duration_seconds.isnot(None),
    ).scalar() or 0

    # Downloads by day
    downloads_by_day = db.query(
        func.date(DownloadQueue.created_at).label("date"),
        func.count(DownloadQueue.id).label("count"),
    ).filter(
        DownloadQueue.created_at >= start_date,
        DownloadQueue.created_at <= end_date,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
    ).group_by(
        func.date(DownloadQueue.created_at)
    ).order_by(
        func.date(DownloadQueue.created_at).desc()
    ).all()

    # Most common quality
    quality_result = db.query(
        DownloadQueue.download_quality,
        func.count(DownloadQueue.id).label("count"),
    ).filter(
        DownloadQueue.created_at >= start_date,
        DownloadQueue.created_at <= end_date,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
        DownloadQueue.download_quality.isnot(None),
    ).group_by(
        DownloadQueue.download_quality
    ).order_by(
        func.count(DownloadQueue.id).desc()
    ).first()

    top_quality = quality_result[0] if quality_result else "N/A"

    # Recent failures with error messages
    recent_failures = db.query(DownloadQueue).filter(
        DownloadQueue.created_at >= start_date,
        DownloadQueue.created_at <= end_date,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.FAILED,
    ).order_by(
        DownloadQueue.created_at.desc()
    ).limit(10).all()

    return {
        "total_downloads": total_downloads,
        "successful_downloads": successful_downloads,
        "failed_downloads": failed_downloads,
        "pending_downloads": pending_downloads,
        "total_data_downloaded": total_data,
        "average_speed_kbps": float(avg_speed) if avg_speed else 0,
        "average_duration_seconds": float(avg_duration) if avg_duration else 0,
        "downloads_by_day": [{"date": str(d.date), "count": d.count} for d in downloads_by_day],
        "top_quality": top_quality,
        "recent_failures": recent_failures,
    }


def _get_recent_log_lines(limit: int = 1000) -> list[str]:
    """
    Get recent lines from the application log file.

    Args:
        limit: Maximum number of lines to return

    Returns:
        List of log lines (newest first)
    """
    # Try to find log file in common locations
    # Construct data path from temp_path (which is /app/data/temp)
    data_path = settings.temp_path.parent

    possible_log_paths = [
        Path("/app/logs/alima.log"),
        Path("logs/alima.log"),
        data_path / "logs" / "alima.log",
    ]

    log_file = None
    for path in possible_log_paths:
        if path.exists():
            log_file = path
            break

    if not log_file:
        return ["No log file found. Checked paths: " + ", ".join(str(p) for p in possible_log_paths)]

    try:
        # Read last N lines from file
        with open(log_file, "r") as f:
            lines = f.readlines()
            # Return last N lines, reversed to show newest first
            return [line.rstrip() for line in reversed(lines[-limit:])]
    except Exception as e:
        return [f"Error reading log file: {e}"]
