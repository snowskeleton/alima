"""Tests for database models and operations."""

import pytest
from sqlalchemy.orm import Session

from app.models import (
    AudibleAccount,
    Book,
    BookSource,
    DownloadQueue,
    DownloadStatus,
    Feed,
    FeedBook,
    FeedType,
    Invite,
    MetadataSource,
    ReplicationConfig,
    ReplicationLog,
    ReplicationMode,
    SyncDirection,
    SyncStatus,
    SyncType,
    User,
    UserRole,
)


@pytest.mark.unit
class TestUserModel:
    """Test User model."""

    def test_create_user(self, test_db: Session):
        """Test creating a user."""
        user = User(
            email="newuser@example.com",
            password_hash="hashed_password",
            role=UserRole.USER,
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.role == UserRole.USER
        assert user.created_at is not None

    def test_user_email_unique(self, test_db: Session, test_user: User):
        """Test that user email must be unique."""
        duplicate_user = User(
            email=test_user.email,
            password_hash="another_password",
            role=UserRole.USER,
        )
        test_db.add(duplicate_user)

        with pytest.raises(Exception):  # SQLAlchemy will raise IntegrityError
            test_db.commit()


@pytest.mark.unit
class TestInviteModel:
    """Test Invite model."""

    def test_create_invite(self, test_db: Session, test_admin: User):
        """Test creating an invite."""
        invite = Invite(
            email="invited@example.com",
            token="unique_token_123",
            role=UserRole.USER,
            created_by=test_admin.id,
            expires_at=test_admin.created_at,  # Use a datetime
            used=False,
        )
        test_db.add(invite)
        test_db.commit()
        test_db.refresh(invite)

        assert invite.id is not None
        assert invite.email == "invited@example.com"
        assert invite.token == "unique_token_123"
        assert invite.used is False
        assert invite.creator.id == test_admin.id


@pytest.mark.unit
class TestAudibleAccountModel:
    """Test AudibleAccount model."""

    def test_create_audible_account(self, test_db: Session):
        """Test creating an Audible account."""
        account = AudibleAccount(
            username="testaccount",
            auth_file_path="/path/to/auth.json",
            activation_bytes="12345678",
            marketplace="US",
            enabled=True,
        )
        test_db.add(account)
        test_db.commit()
        test_db.refresh(account)

        assert account.id is not None
        assert account.username == "testaccount"
        assert account.marketplace == "US"
        assert account.enabled is True


@pytest.mark.unit
class TestBookModel:
    """Test Book model."""

    def test_create_audible_book(self, test_db: Session):
        """Test creating an Audible book."""
        account = AudibleAccount(
            username="testuser",
            auth_file_path="/path/to/auth.json",
            activation_bytes="12345678",
            marketplace="US",
            enabled=True,
        )
        test_db.add(account)
        test_db.commit()

        book = Book(
            asin="B001234567",
            audible_account_id=account.id,
            source=BookSource.AUDIBLE,
            title="Test Book",
            author="Test Author",
            metadata_source=MetadataSource.AUDIBLE,
            synced_from_master=False,
        )
        test_db.add(book)
        test_db.commit()
        test_db.refresh(book)

        assert book.id is not None
        assert book.asin == "B001234567"
        assert book.source == BookSource.AUDIBLE
        assert book.title == "Test Book"

    def test_create_imported_book(self, test_db: Session):
        """Test creating an imported book."""
        book = Book(
            source=BookSource.IMPORTED,
            title="Imported Book",
            file_path="/path/to/book.m4b",
            metadata_source=MetadataSource.FILE,
            synced_from_master=False,
        )
        test_db.add(book)
        test_db.commit()
        test_db.refresh(book)

        assert book.id is not None
        assert book.source == BookSource.IMPORTED
        assert book.asin is None


@pytest.mark.unit
class TestFeedModel:
    """Test Feed model."""

    def test_create_smart_feed(self, test_db: Session, test_user: User):
        """Test creating a smart feed."""
        feed = Feed(
            user_id=test_user.id,
            name="Fantasy Books",
            feed_type=FeedType.SMART,
            filter_criteria={"type": "genre", "value": "Fantasy"},
            slug="fantasy-books",
            is_public=True,
        )
        test_db.add(feed)
        test_db.commit()
        test_db.refresh(feed)

        assert feed.id is not None
        assert feed.feed_type == FeedType.SMART
        assert feed.filter_criteria["type"] == "genre"

    def test_create_manual_feed(self, test_db: Session, test_user: User):
        """Test creating a manual feed."""
        feed = Feed(
            user_id=test_user.id,
            name="My Favorites",
            feed_type=FeedType.MANUAL,
            slug="my-favorites",
            is_public=False,
        )
        test_db.add(feed)
        test_db.commit()
        test_db.refresh(feed)

        assert feed.id is not None
        assert feed.feed_type == FeedType.MANUAL
        assert feed.is_public is False


@pytest.mark.unit
class TestDownloadQueueModel:
    """Test DownloadQueue model."""

    def test_create_download_queue_entry(self, test_db: Session):
        """Test creating a download queue entry."""
        account = AudibleAccount(
            username="testuser",
            auth_file_path="/path/to/auth.json",
            activation_bytes="12345678",
            marketplace="US",
            enabled=True,
        )
        test_db.add(account)
        test_db.commit()

        book = Book(
            asin="B001234567",
            audible_account_id=account.id,
            source=BookSource.AUDIBLE,
            title="Test Book",
            metadata_source=MetadataSource.AUDIBLE,
            synced_from_master=False,
        )
        test_db.add(book)
        test_db.commit()

        queue_entry = DownloadQueue(
            book_id=book.id,
            audible_account_id=account.id,
            asin="B001234567",
            priority=1,
            status=DownloadStatus.PENDING,
            attempts=0,
        )
        test_db.add(queue_entry)
        test_db.commit()
        test_db.refresh(queue_entry)

        assert queue_entry.id is not None
        assert queue_entry.status == DownloadStatus.PENDING
        assert queue_entry.attempts == 0


@pytest.mark.unit
class TestReplicationModels:
    """Test Replication models."""

    def test_create_replication_config(self, test_db: Session):
        """Test creating replication config."""
        config = ReplicationConfig(
            instance_id="uuid-123",
            instance_name="Master Instance",
            mode=ReplicationMode.MASTER,
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        assert config.id is not None
        assert config.mode == ReplicationMode.MASTER

    def test_create_replication_log(self, test_db: Session):
        """Test creating replication log."""
        log = ReplicationLog(
            sync_type=SyncType.BOOK_METADATA,
            direction=SyncDirection.PUSH,
            status=SyncStatus.COMPLETED,
            items_synced=10,
            bytes_transferred=1024000,
        )
        test_db.add(log)
        test_db.commit()
        test_db.refresh(log)

        assert log.id is not None
        assert log.sync_type == SyncType.BOOK_METADATA
        assert log.items_synced == 10
