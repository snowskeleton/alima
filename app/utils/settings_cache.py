"""Centralized cached settings accessor to replace duplicate database queries."""

import logging
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)


@lru_cache(maxsize=128)
def get_cached_setting(key: str, default: Any = None, value_type: type = str) -> Any:
    """
    Get a setting value from the database with caching.

    This replaces the pattern of manually creating a SessionLocal, querying
    SettingsService, and closing the session. Results are cached in memory
    to avoid repeated database queries.

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
    try:
        from ..database import SessionLocal
        from ..services.settings_service import SettingsService

        db = SessionLocal()
        try:
            settings_service = SettingsService(db)
            value = settings_service.get(key)

            if value is None:
                return default

            # Type conversion
            if value_type == int:
                return int(value)
            elif value_type == float:
                return float(value)
            elif value_type == bool:
                # Handle bool conversion properly
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "on")
                return bool(value)
            else:
                return str(value)

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Failed to get setting '{key}': {e}, using default: {default}")
        return default


def clear_settings_cache() -> None:
    """
    Clear the settings cache.

    Call this when settings are updated to force a fresh database query
    on the next access.
    """
    get_cached_setting.cache_clear()
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
        from ..database import SessionLocal
        from ..services.settings_service import SettingsService

        db = SessionLocal()
        try:
            settings_service = SettingsService(db)
            value = settings_service.get(key)
            return value if value is not None else default
        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Failed to get setting '{key}': {e}, using default: {default}")
        return default
