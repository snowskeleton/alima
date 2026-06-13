"""API v2 routes for log viewing."""

from pathlib import Path

from fastapi import APIRouter, Depends, Query

from ...dependencies import require_admin
from ...models import User

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("")
async def get_logs(
    view: str = Query("stats"),
    lines: int = Query(200, le=5000),
    current_user: User = Depends(require_admin),
):
    """Get application logs."""
    log_dir = Path("/app/data/logs") if Path("/app").exists() else Path("data/logs")

    if view == "stats":
        result = {}
        for log_file in ["alima.log", "alima-error.log"]:
            path = log_dir / log_file
            if path.exists():
                result[log_file] = {
                    "size_bytes": path.stat().st_size,
                    "modified": path.stat().st_mtime,
                }
        return {"stats": result}

    elif view == "downloads":
        log_path = log_dir / "alima.log"
        if not log_path.exists():
            return {"lines": []}

        all_lines = log_path.read_text().splitlines()
        download_lines = [
            line for line in all_lines
            if "download" in line.lower() or "queue" in line.lower()
        ]
        return {"lines": download_lines[-lines:]}

    else:  # raw
        log_path = log_dir / "alima.log"
        if not log_path.exists():
            return {"lines": []}

        all_lines = log_path.read_text().splitlines()
        return {"lines": all_lines[-lines:]}
