"""API v2 routes for log viewing."""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...database import get_db
from ...dependencies import require_admin
from ...models import DownloadQueue, DownloadStatus, DownloadType, User

router = APIRouter(prefix="/logs", tags=["Logs"])

LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+) - ([\w.]+) - (DEBUG|INFO|WARNING|ERROR|CRITICAL) - (.+)$"
)


def _find_log_file() -> Path | None:
    for path in [Path("/app/data/logs/alima.log"), Path("data/logs/alima.log")]:
        if path.exists():
            return path
    return None


def _parse_log_line(line: str) -> dict | None:
    m = LOG_LINE_RE.match(line)
    if not m:
        return None
    ts_raw, module, level, message = m.groups()
    return {
        "timestamp": ts_raw.replace(",", "."),
        "module": module.split(".")[-1],
        "level": level,
        "message": message,
    }


@router.get("")
async def get_logs(
    view: str = Query("raw"),
    days: int = Query(7, ge=1, le=90),
    lines: int = Query(500, ge=1, le=5000),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if view == "stats":
        return _get_stats(db, days)
    elif view == "downloads":
        return _get_downloads(db, days)
    else:
        return _get_raw_logs(lines)


def _get_stats(db: Session, days: int) -> dict:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    def book_query():
        return db.query(DownloadQueue).filter(
            DownloadQueue.created_at >= start,
            DownloadQueue.created_at <= end,
            DownloadQueue.download_type == DownloadType.BOOK,
        )

    total = book_query().count()
    successful = book_query().filter(DownloadQueue.status == DownloadStatus.COMPLETED).count()
    failed = book_query().filter(DownloadQueue.status == DownloadStatus.FAILED).count()

    pending = db.query(DownloadQueue).filter(
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status.in_([DownloadStatus.PENDING, DownloadStatus.DOWNLOADING, DownloadStatus.DECRYPTING]),
    ).count()

    total_bytes = db.query(func.sum(DownloadQueue.file_size_bytes)).filter(
        DownloadQueue.created_at >= start,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
        DownloadQueue.file_size_bytes.isnot(None),
    ).scalar() or 0

    avg_speed = db.query(func.avg(DownloadQueue.download_speed_kbps)).filter(
        DownloadQueue.created_at >= start,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
        DownloadQueue.download_speed_kbps.isnot(None),
    ).scalar() or 0

    avg_duration = db.query(func.avg(DownloadQueue.duration_seconds)).filter(
        DownloadQueue.created_at >= start,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
        DownloadQueue.duration_seconds.isnot(None),
    ).scalar() or 0

    by_day = db.query(
        func.date(DownloadQueue.created_at).label("date"),
        func.count(DownloadQueue.id).label("count"),
    ).filter(
        DownloadQueue.created_at >= start,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
    ).group_by(func.date(DownloadQueue.created_at)).order_by(func.date(DownloadQueue.created_at).desc()).all()

    quality_row = db.query(
        DownloadQueue.download_quality,
        func.count(DownloadQueue.id).label("count"),
    ).filter(
        DownloadQueue.created_at >= start,
        DownloadQueue.download_type == DownloadType.BOOK,
        DownloadQueue.status == DownloadStatus.COMPLETED,
        DownloadQueue.download_quality.isnot(None),
    ).group_by(DownloadQueue.download_quality).order_by(func.count(DownloadQueue.id).desc()).first()

    recent_failures = book_query().filter(
        DownloadQueue.status == DownloadStatus.FAILED
    ).order_by(DownloadQueue.created_at.desc()).limit(10).all()

    return {
        "total_downloads": total,
        "successful_downloads": successful,
        "failed_downloads": failed,
        "pending_downloads": pending,
        "total_bytes": total_bytes,
        "average_speed_kbps": float(avg_speed),
        "average_duration_seconds": float(avg_duration),
        "downloads_by_day": [{"date": str(r.date), "count": r.count} for r in by_day],
        "top_quality": quality_row[0] if quality_row else None,
        "recent_failures": [
            {
                "asin": f.asin,
                "book_title": f.book.title if f.book else None,
                "created_at": f.created_at.isoformat(),
                "error_message": f.error_message,
            }
            for f in recent_failures
        ],
    }


def _get_downloads(db: Session, days: int) -> dict:
    start = datetime.now(timezone.utc) - timedelta(days=days)
    entries = (
        db.query(DownloadQueue)
        .filter(
            DownloadQueue.created_at >= start,
            DownloadQueue.download_type == DownloadType.BOOK,
        )
        .order_by(DownloadQueue.created_at.desc())
        .limit(1000)
        .all()
    )
    return {
        "downloads": [
            {
                "id": e.id,
                "asin": e.asin,
                "book_title": e.book.title if e.book else None,
                "status": e.status.value,
                "file_size_bytes": e.file_size_bytes,
                "duration_seconds": e.duration_seconds,
                "download_speed_kbps": e.download_speed_kbps,
                "download_quality": e.download_quality,
                "attempts": e.attempts,
                "error_message": e.error_message,
                "created_at": e.created_at.isoformat(),
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
            }
            for e in entries
        ]
    }


def _get_raw_logs(lines: int) -> dict:
    log_file = _find_log_file()
    if not log_file:
        return {"entries": []}

    all_lines = log_file.read_text(errors="replace").splitlines()
    recent = all_lines[-lines:]

    entries = []
    for line in reversed(recent):
        parsed = _parse_log_line(line)
        if parsed:
            entries.append(parsed)
        elif line.strip():
            entries.append({"timestamp": None, "module": None, "level": "OTHER", "message": line.strip()})

    return {"entries": entries}
