"""Database session management and initialization."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base

# Create engine
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
    # echo=settings.environment == "development",
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
    # Ensure database directory exists
    db_path = settings.database_url.replace("sqlite:///", "")
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

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
