"""SQLAlchemy database models for Alima."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# Enums
class UserRole(str, PyEnum):
    """User role enumeration."""

    ADMIN = "admin"
    USER = "user"


class BookSource(str, PyEnum):
    """Book source enumeration."""

    AUDIBLE = "audible"
    IMPORTED = "imported"


class MetadataSource(str, PyEnum):
    """Metadata source enumeration."""

    AUDIBLE = "audible"
    FILE = "file"
    MANUAL = "manual"


class FeedType(str, PyEnum):
    """Feed type enumeration."""

    SMART = "smart"
    MANUAL = "manual"


class DownloadStatus(str, PyEnum):
    """Download queue status enumeration."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    DECRYPTING = "decrypting"
    COMPLETED = "completed"
    FAILED = "failed"


class DownloadType(str, PyEnum):
    """Download type enumeration."""

    BOOK = "BOOK"
    COVER = "COVER"


class ReplicationMode(str, PyEnum):
    """Replication mode enumeration."""

    MASTER = "master"
    SLAVE = "slave"
    STANDALONE = "standalone"


class SyncType(str, PyEnum):
    """Replication sync type enumeration."""

    BOOK_METADATA = "book_metadata"
    FILE_TRANSFER = "file_transfer"
    FEED_SYNC = "feed_sync"
    FULL = "full"


class SyncDirection(str, PyEnum):
    """Replication sync direction enumeration."""

    PUSH = "push"
    PULL = "pull"


class SyncStatus(str, PyEnum):
    """Replication sync status enumeration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(str, PyEnum):
    """Background job status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditStatus(str, PyEnum):
    """Library audit run status enumeration."""

    SCANNING = "scanning"
    COMPLETED = "completed"
    FAILED = "failed"


# Models
class User(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    receive_notifications: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # Relationships
    feeds: Mapped[list["Feed"]] = relationship("Feed", back_populates="user")


class MagicLink(Base):
    """Magic link token model for passwordless authentication."""

    __tablename__ = "magic_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AudibleAccount(Base):
    """Audible account model."""

    __tablename__ = "audible_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True)
    auth_file_path: Mapped[str] = mapped_column(String(512))
    activation_bytes: Mapped[str] = mapped_column(String(16))
    marketplace: Mapped[str] = mapped_column(String(10))
    last_sync_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    downloads_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    books: Mapped[list["Book"]] = relationship("Book", back_populates="audible_account")
    download_queue: Mapped[list["DownloadQueue"]] = relationship(
        "DownloadQueue", back_populates="audible_account",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class Book(Base):
    """Book model."""

    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asin: Mapped[Optional[str]] = mapped_column(
        String(32), unique=True, nullable=True, index=True
    )
    audible_account_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("audible_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[BookSource] = mapped_column(Enum(BookSource), index=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, index=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    file_format: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    b2_audio_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    b2_cover_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    download_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    download_unavailable: Mapped[bool] = mapped_column(Boolean, default=False)
    download_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    title: Mapped[str] = mapped_column(String(512))
    subtitle: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    author: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    narrator: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    series: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    series_position: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    publish_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cover_image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    genres: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Metadata tracking
    metadata_source: Mapped[MetadataSource] = mapped_column(
        Enum(MetadataSource), default=MetadataSource.AUDIBLE
    )
    metadata_override: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_metadata_update: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Replication fields
    synced_from_master: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    master_book_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_replicated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # Timestamps
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    purchased_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_modified: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    audible_account: Mapped[Optional["AudibleAccount"]] = relationship(
        "AudibleAccount", back_populates="books"
    )
    # cascade + passive_deletes: these children have NOT NULL FKs declared
    # ON DELETE CASCADE. Without this, deleting the parent makes SQLAlchemy try
    # to null the child's FK first, which the database rejects.
    feed_books: Mapped[list["FeedBook"]] = relationship(
        "FeedBook", back_populates="book",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    download_queue: Mapped[Optional["DownloadQueue"]] = relationship(
        "DownloadQueue", back_populates="book",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class Feed(Base):
    """RSS Feed model."""

    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feed_type: Mapped[FeedType] = mapped_column(Enum(FeedType))

    # For smart feeds
    filter_criteria: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Feed settings
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    cover_image_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="feeds")
    feed_books: Mapped[list["FeedBook"]] = relationship(
        "FeedBook", back_populates="feed",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class FeedBook(Base):
    """Feed-Book junction table (for manual feeds)."""

    __tablename__ = "feed_books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(Integer, ForeignKey("feeds.id", ondelete="CASCADE"))
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    feed: Mapped["Feed"] = relationship("Feed", back_populates="feed_books")
    book: Mapped["Book"] = relationship("Book", back_populates="feed_books")


class DownloadQueue(Base):
    """Download queue model."""

    __tablename__ = "download_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"))
    audible_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("audible_accounts.id", ondelete="CASCADE")
    )
    asin: Mapped[str] = mapped_column(String(32))
    download_type: Mapped[DownloadType] = mapped_column(
        Enum(DownloadType), default=DownloadType.BOOK
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[DownloadStatus] = mapped_column(
        Enum(DownloadStatus), default=DownloadStatus.PENDING, index=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Liveness signal for an in-flight entry. bytes_downloaded is the count the
    # worker last reported (bytes written for a download, bytes decrypted for a
    # decrypt); progress_at is when it last changed. Staleness is judged on
    # progress_at, so a slow-but-moving transfer is never reaped.
    bytes_downloaded: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    total_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    progress_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # When the *current* phase began. started_at marks the whole attempt and is
    # what the duration metrics are built on, so rates for the decrypt phase
    # need their own origin or they'd include the download time.
    phase_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Download metrics (nullable since existing records won't have these)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    download_speed_kbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    download_quality: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Read/unread tracking (global, not per-user)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    book: Mapped["Book"] = relationship("Book", back_populates="download_queue")
    audible_account: Mapped["AudibleAccount"] = relationship(
        "AudibleAccount", back_populates="download_queue"
    )


class ReplicationConfig(Base):
    """Replication configuration model."""

    __tablename__ = "replication_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(String(36), unique=True)
    instance_name: Mapped[str] = mapped_column(String(255))
    mode: Mapped[ReplicationMode] = mapped_column(
        Enum(ReplicationMode), default=ReplicationMode.STANDALONE
    )
    paired_instance_url: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    paired_instance_api_key: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    last_sync_from_master: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ReplicationLog(Base):
    """Replication log model."""

    __tablename__ = "replication_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_type: Mapped[SyncType] = mapped_column(Enum(SyncType))
    direction: Mapped[SyncDirection] = mapped_column(Enum(SyncDirection))
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus), default=SyncStatus.PENDING
    )
    items_synced: Mapped[int] = mapped_column(Integer, default=0)
    bytes_transferred: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ApiKey(Base):
    """API key model for programmatic access."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    key_prefix: Mapped[str] = mapped_column(String(8))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User")


class ServerSettings(Base):
    """Server configuration settings stored in database."""

    __tablename__ = "server_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(50), default="general")
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )


class AuditRun(Base):
    """Library audit run tracking model."""

    __tablename__ = "audit_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus), default=AuditStatus.SCANNING
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    mismatches: Mapped[int] = mapped_column(Integer, default=0)
    missing_files: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    results: Mapped[list["AuditResult"]] = relationship(
        "AuditResult", back_populates="audit_run", cascade="all, delete-orphan"
    )


class AuditResult(Base):
    """Individual book result from a library audit run."""

    __tablename__ = "audit_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    book_title: Mapped[str] = mapped_column(String(512))
    book_author: Mapped[str] = mapped_column(String(512))
    file_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    file_author: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    title_score: Mapped[float] = mapped_column(Float, default=0.0)
    author_score: Mapped[float] = mapped_column(Float, default=0.0)
    file_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(20))

    # Relationships
    audit_run: Mapped["AuditRun"] = relationship("AuditRun", back_populates="results")


class BackgroundJob(Base):
    """Background job tracking model for non-blocking operations."""

    __tablename__ = "background_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
