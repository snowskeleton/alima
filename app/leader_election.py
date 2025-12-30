"""Leader election using PostgreSQL advisory locks."""

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .config import settings

logger = logging.getLogger(__name__)


class LeaderElection:
    """
    Manages leader election using PostgreSQL advisory locks.

    Ensures only one Gunicorn worker performs startup tasks like
    migrations, scheduler startup, and system feed creation.
    """

    # Lock ID: first 8 hex digits of MD5("alima") as int
    LOCK_ID: int = 0x17D9F6E9  # 399987465

    _lock_connection: Optional[Connection] = None
    _is_leader: bool = False

    @classmethod
    def try_acquire_leadership(cls) -> bool:
        """
        Attempt to acquire leader lock.

        Returns:
            True if this worker is now the leader, False otherwise.
        """
        import os

        # Skip if not PostgreSQL
        if not settings.database_url.startswith("postgresql"):
            logger.info("Non-PostgreSQL database, assuming leader role")
            cls._is_leader = True
            return True

        try:
            # Import main engine (avoid circular import)
            from .database import engine

            # Get connection from main application pool
            # Note: This connection must be held for the app's lifetime to maintain the lock
            cls._lock_connection = engine.connect()

            # Try to acquire advisory lock (non-blocking)
            result = cls._lock_connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": cls.LOCK_ID}
            ).scalar()

            cls._is_leader = bool(result)

            if cls._is_leader:
                logger.info(
                    f"Worker {os.getpid()} acquired leader lock "
                    f"(connection will be held for app lifetime)"
                )
            else:
                logger.info(f"Worker {os.getpid()} is follower (lock held by another worker)")
                # Close connection if not leader (return to pool)
                cls._lock_connection.close()
                cls._lock_connection = None

            return cls._is_leader

        except Exception as e:
            logger.warning(f"Leader election failed: {e}, assuming leader role (fail-safe)")
            cls._is_leader = True
            return True

    @classmethod
    def is_leader(cls) -> bool:
        """Check if this worker is the leader."""
        return cls._is_leader

    @classmethod
    def release_leadership(cls) -> None:
        """Release leader lock (called on shutdown)."""
        if cls._lock_connection:
            try:
                cls._lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": cls.LOCK_ID}
                )
                cls._lock_connection.close()
                logger.info("Released leader lock")
            except Exception as e:
                logger.warning(f"Error releasing leader lock: {e}")
            finally:
                cls._lock_connection = None
                cls._is_leader = False
