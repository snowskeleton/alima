"""Database session management and initialization."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base

# Create engine with proper connection pooling
# With 4 Gunicorn workers + scheduler threads + download threads:
# - Base: 10 connections per worker
# - Overflow: 5 additional connections under load
# - Total max per worker: 15 connections
# - Total potential across 4 workers: 60 connections (safe margin under PostgreSQL default of 100)
engine = create_engine(
    settings.database_url,
    echo=False,
    # echo=settings.environment == "development",
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,        # Base connections per worker
    max_overflow=5,      # Extra connections under load
    pool_recycle=3600,   # Recycle connections hourly (prevents stale connections)
    pool_timeout=30,     # Wait up to 30s for connection
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database session.

    Yields:
        Database session that is automatically closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database by creating all tables.

    This function should be called during application startup or via CLI.
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create system "all" feed if it doesn't exist
    _create_system_feed()


def _create_system_feed() -> None:
    """
    Create the system "all" feed if it doesn't exist.

    This feed shows all books and is accessible to everyone at /feed/all.
    """
    from .models import Feed, FeedType

    db = SessionLocal()
    try:
        # Check if system feed already exists
        existing_feed = db.query(Feed).filter(Feed.slug == "all").first()

        if existing_feed:
            return  # Already exists

        # Create the system feed
        system_feed = Feed(
            user_id=None,  # No owner (system feed)
            name="All Books",
            description="All books in the library",
            feed_type=FeedType.SMART,
            filter_criteria=None,  # No filter = all books
            is_public=True,
            is_system=True,
            is_pinned=False,
            slug="all",
        )

        db.add(system_feed)
        db.commit()
        print("Created system 'all' feed")

    except Exception as e:
        print(f"Error creating system feed: {e}")
        db.rollback()
    finally:
        db.close()


def drop_db() -> None:
    """
    Drop all database tables.

    WARNING: This will delete all data. Use with caution.
    """
    Base.metadata.drop_all(bind=engine)
