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
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole


# Use shared in-memory SQLite for tests
# Important: Use file: with cache=shared to share the database across connections
TEST_DATABASE_URL = "sqlite:///file:test_db?mode=memory&cache=shared&uri=true"


@pytest.fixture(scope="function")
def test_engine():
    """Create a test database engine."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False, "uri": True},
    )

    # SQLite ignores foreign keys unless asked. Production runs PostgreSQL, which
    # always enforces them, so turn them on here to keep the test database honest
    # about ON DELETE CASCADE.
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
