"""Centralized cached settings accessor to replace duplicate database queries.

The cache is per-process and the app runs under gunicorn with several workers,
so an explicit invalidation only ever clears the cache of the worker that
handled the request. Entries therefore also expire on a short timer, which is
what makes a settings change reach every worker: the saving worker updates
instantly, the rest converge within CACHE_TTL_SECONDS.

That bound matters — settings include credentials (SMTP, Backblaze B2), and
without it a rotated credential would keep failing in the other workers until
the process restarted.
"""

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# How long a cached setting stays valid. Long enough to collapse the burst of
# reads a single request makes, short enough that a settings change propagates
# to every worker while the admin is still looking at the page.
CACHE_TTL_SECONDS = 5.0

# (key, default, value_type) -> (value, expires_at_monotonic)
_cache: dict[tuple, tuple[Any, float]] = {}
_lock = threading.Lock()


def _read_setting(key: str, default: Any, value_type: type) -> Any:
    """Read a single setting straight from the database."""
    from ..database import SessionLocal
    from ..services.settings_service import SettingsService

    db = SessionLocal()
    try:
        value = SettingsService(db).get(key)

        if value is None:
            return default

        if value_type == int:
            return int(value)
        elif value_type == float:
            return float(value)
        elif value_type == bool:
            if isinstance(value, str):
                return value.strip().lower() in ("true", "1", "yes", "on")
            return bool(value)
        else:
            return str(value)

    finally:
        db.close()


def get_cached_setting(key: str, default: Any = None, value_type: type = str) -> Any:
    """
    Get a setting value from the database, cached for CACHE_TTL_SECONDS.

    Args:
        key: Setting key to retrieve
        default: Default value if setting not found
        value_type: Type to convert the value to (str, int, float, bool)

    Returns:
        The setting value converted to value_type, or default if not found

    Example:
        >>> quick_sync_interval = get_cached_setting("quick_sync_interval_minutes", 1, int)
        >>> smtp_host = get_cached_setting("smtp_host", "localhost", str)
    """
    cache_key = (key, default, value_type)
    now = time.monotonic()

    with _lock:
        entry = _cache.get(cache_key)
        if entry is not None and entry[1] > now:
            return entry[0]

    # Read outside the lock — this touches the database, and holding the lock
    # would serialise every worker thread behind one query.
    try:
        value = _read_setting(key, default, value_type)
    except Exception as e:
        logger.warning(f"Failed to get setting '{key}': {e}, using default: {default}")
        return default

    with _lock:
        _cache[cache_key] = (value, time.monotonic() + CACHE_TTL_SECONDS)

    return value


def clear_settings_cache() -> None:
    """
    Clear this process's settings cache.

    Call after writing settings so the worker handling the request sees the new
    values immediately. Other workers pick them up when their entries expire.
    """
    with _lock:
        _cache.clear()
    logger.info("Settings cache cleared")


def get_setting_no_cache(key: str, default: Any = None) -> Any:
    """
    Get a setting value without caching (for real-time updates).

    Use this only when you need the absolute latest value and can't
    tolerate cache staleness. Prefer get_cached_setting for performance.

    Args:
        key: Setting key to retrieve
        default: Default value if setting not found

    Returns:
        The setting value, or default if not found
    """
    try:
        return _read_setting(key, default, str)
    except Exception as e:
        logger.warning(f"Failed to get setting '{key}': {e}, using default: {default}")
        return default
