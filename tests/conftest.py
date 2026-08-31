"""Pytest configuration and shared fixtures."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Set testing environment BEFORE importing app modules
os.environ["ENVIRONMENT"] = "testing"
# Disable SMTP in tests to prevent any real email sending
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_USER"] = ""
os.environ["SMTP_PASSWORD"] = ""
os.environ["SMTP_FROM"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole


# Shared in-memory SQLite by default: file: with cache=shared so the database is
# visible across connections.
#
# Overridable via TEST_DATABASE_URL so CI can run the same suite against
# Postgres, which is what production uses. SQLite and Postgres disagree about
# enough -- constraint timing, JSON columns, integer width, case sensitivity --
# that a suite which only ever sees SQLite will miss real bugs.
SQLITE_TEST_URL = "sqlite:///file:test_db?mode=memory&cache=shared&uri=true"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or SQLITE_TEST_URL

RUNNING_ON_SQLITE = TEST_DATABASE_URL.startswith("sqlite")


@pytest.fixture(scope="function")
def test_engine():
    """Create a test database engine."""
    if RUNNING_ON_SQLITE:
        engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"check_same_thread": False, "uri": True},
        )
    else:
        # Each test gets a clean schema, so pooling connections between tests
        # only risks holding a transaction open across the drop_all below.
        engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)

    # SQLite ignores foreign keys unless asked. Production runs PostgreSQL, which
    # always enforces them, so turn them on here to keep the test database honest
    # about ON DELETE CASCADE.
    if RUNNING_ON_SQLITE:

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db(test_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def mock_email_service():
    """Mock EmailService to prevent sending real emails during tests."""
    with patch("app.services.email_service.EmailService.send_invite_email", new_callable=AsyncMock) as mock_send_invite, \
         patch("app.services.email_service.EmailService.send_test_email", new_callable=AsyncMock) as mock_send_test, \
         patch("app.services.email_service.EmailService.send_magic_link_email", new_callable=AsyncMock) as mock_send_magic:

        # Mock all email methods to return True (success)
        mock_send_invite.return_value = True
        mock_send_test.return_value = True
        mock_send_magic.return_value = True

        yield {
            "send_invite_email": mock_send_invite,
            "send_test_email": mock_send_test,
            "send_magic_link_email": mock_send_magic,
        }


@pytest.fixture(scope="function")
def client(test_engine, mock_email_service):
    """Create a test client with test database and mocked email."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def test_user(test_db: Session) -> User:
    """Create a test user."""
    from app.auth import get_password_hash

    user = User(
        email="test@example.com",
        password_hash=get_password_hash("testpassword"),
        role=UserRole.USER,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_admin(test_db: Session) -> User:
    """Create a test admin user."""
    from app.auth import get_password_hash

    admin = User(
        email="admin@example.com",
        password_hash=get_password_hash("adminpassword"),
        role=UserRole.ADMIN,
    )
    test_db.add(admin)
    test_db.commit()
    test_db.refresh(admin)
    return admin


@pytest.fixture
def authenticated_client(client: TestClient, test_user: User):
    """Create an authenticated test client."""
    from app.auth import create_access_token

    token = create_access_token(data={"sub": test_user.email, "user_id": test_user.id})
    client.cookies.set("session_token", token)
    return client


@pytest.fixture
def admin_client(client: TestClient, test_admin: User):
    """Create an authenticated admin test client."""
    from app.auth import create_access_token

    token = create_access_token(
        data={"sub": test_admin.email, "user_id": test_admin.id}
    )
    client.cookies.set("session_token", token)
    return client


def issue_api_key(
    db: Session,
    user: User,
    name: str = "test key",
    expires_at=None,
) -> str:
    """Mint an API key for a user and return the raw key (only time it exists)."""
    import hashlib
    import secrets

    from app.models import ApiKey

    raw_key = secrets.token_urlsafe(32)
    db.add(
        ApiKey(
            user_id=user.id,
            name=name,
            key_prefix=raw_key[:8],
            key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
            expires_at=expires_at,
        )
    )
    db.commit()
    return raw_key


@pytest.fixture
def user_api_key(test_db: Session, test_user: User) -> str:
    """Raw API key belonging to the regular test user."""
    return issue_api_key(test_db, test_user, "user key")


@pytest.fixture
def admin_api_key(test_db: Session, test_admin: User) -> str:
    """Raw API key belonging to the admin test user."""
    return issue_api_key(test_db, test_admin, "admin key")


# ---------------------------------------------------------------------------
# Domain fixtures
#
# Factories rather than bare fixtures: most router tests need several books or
# feeds with differing attributes, and a single fixed instance forces tests to
# mutate shared state to say what they mean.
# ---------------------------------------------------------------------------


@pytest.fixture
def make_book(test_db: Session):
    """Create a Book. Only `title` is really required; the rest has defaults."""
    from datetime import datetime

    from app.models import Book, BookSource, MetadataSource

    created = []

    def _make(**overrides):
        now = datetime.utcnow()
        defaults = dict(
            title=f"Book {len(created) + 1}",
            author="An Author",
            asin=f"ASIN{len(created) + 1:08d}",
            source=BookSource.AUDIBLE,
            metadata_source=MetadataSource.AUDIBLE,
            last_metadata_update=now,
            added_at=now,
            last_modified=now,
        )
        book = Book(**{**defaults, **overrides})
        test_db.add(book)
        test_db.commit()
        test_db.refresh(book)
        created.append(book)
        return book

    return _make


@pytest.fixture
def test_book(make_book):
    return make_book()


@pytest.fixture
def make_feed(test_db: Session):
    """Create a Feed owned by a given user."""
    from datetime import datetime

    from app.models import Feed, FeedType

    created = []

    def _make(owner, **overrides):
        now = datetime.utcnow()
        n = len(created) + 1
        defaults = dict(
            user_id=owner.id,
            name=f"Feed {n}",
            feed_type=FeedType.MANUAL,
            slug=f"feed-{n}",
            is_public=False,
            created_at=now,
            updated_at=now,
        )
        feed = Feed(**{**defaults, **overrides})
        test_db.add(feed)
        test_db.commit()
        test_db.refresh(feed)
        created.append(feed)
        return feed

    return _make


@pytest.fixture
def make_account(test_db: Session):
    """Create an AudibleAccount."""
    from datetime import datetime

    from app.models import AudibleAccount

    created = []

    def _make(**overrides):
        n = len(created) + 1
        defaults = dict(
            username=f"account{n}@example.com",
            auth_file_path=f"account{n}.json",
            activation_bytes="deadbeef",
            marketplace="us",
            added_at=datetime.utcnow(),
        )
        account = AudibleAccount(**{**defaults, **overrides})
        test_db.add(account)
        test_db.commit()
        test_db.refresh(account)
        created.append(account)
        return account

    return _make


@pytest.fixture
def make_queue_entry(test_db: Session):
    """Create a DownloadQueue entry for a book/account pair."""
    from datetime import datetime

    from app.models import DownloadQueue, DownloadStatus, DownloadType

    def _make(book, account, **overrides):
        defaults = dict(
            book_id=book.id,
            audible_account_id=account.id,
            asin=book.asin or "ASINDEFAULT",
            download_type=DownloadType.BOOK,
            status=DownloadStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        entry = DownloadQueue(**{**defaults, **overrides})
        test_db.add(entry)
        test_db.commit()
        test_db.refresh(entry)
        return entry

    return _make


@pytest.fixture
def second_user(test_db: Session) -> User:
    """A second regular user, for cross-tenant permission tests."""
    user = User(email="other@example.com", role=UserRole.USER)
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def json_headers():
    """Force JSON error responses rather than browser login redirects."""
    return {"Accept": "application/json"}
