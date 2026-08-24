"""Tests for authentication functionality."""

import pytest
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    create_magic_link,
    create_user,
    get_password_hash,
    update_last_login,
    verify_magic_link,
    verify_password,
    verify_token,
)
from app.models import User


@pytest.mark.unit
class TestPasswordHashing:
    """Test password hashing functions (backward compat)."""

    def test_password_hash(self):
        """Test password hashing."""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert hashed != password

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False


@pytest.mark.unit
class TestJWTTokens:
    """Test JWT token operations."""

    def test_create_access_token(self):
        """Test creating an access token."""
        data = {"sub": "test@example.com", "user_id": 1}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_token_valid(self):
        """Test verifying a valid token."""
        data = {"sub": "test@example.com", "user_id": 1}
        token = create_access_token(data)

        token_data = verify_token(token)

        assert token_data is not None
        assert token_data.email == "test@example.com"
        assert token_data.user_id == 1

    def test_verify_token_invalid(self):
        """Test verifying an invalid token."""
        invalid_token = "invalid.token.string"

        token_data = verify_token(invalid_token)

        assert token_data is None


@pytest.mark.unit
class TestMagicLinks:
    """Test magic link creation and verification."""

    def test_create_magic_link(self, test_db: Session, test_user: User):
        """Test creating a magic link."""
        token = create_magic_link(test_db, test_user.email)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_magic_link_valid(self, test_db: Session, test_user: User):
        """Test verifying a valid magic link."""
        token = create_magic_link(test_db, test_user.email)
        user = verify_magic_link(test_db, token)

        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email

    def test_verify_magic_link_invalid(self, test_db: Session):
        """Test verifying an invalid magic link."""
        user = verify_magic_link(test_db, "nonexistent-token")
        assert user is None

    def test_verify_magic_link_used_twice(self, test_db: Session, test_user: User):
        """Test that a magic link can only be used once."""
        token = create_magic_link(test_db, test_user.email)

        # First use should succeed
        user = verify_magic_link(test_db, token)
        assert user is not None

        # Second use should fail
        user2 = verify_magic_link(test_db, token)
        assert user2 is None

    def test_verify_magic_link_no_user(self, test_db: Session):
        """Test magic link for nonexistent user returns None."""
        token = create_magic_link(test_db, "nonexistent@example.com")
        user = verify_magic_link(test_db, token)
        assert user is None


@pytest.mark.unit
class TestUserCreation:
    """Test user creation."""

    def test_create_user_without_password(self, test_db: Session):
        """Test creating a user without a password (magic link only)."""
        user = create_user(test_db, "newuser@example.com", role="user")

        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.role.value == "user"
        assert user.password_hash is None

    def test_create_user_with_password(self, test_db: Session):
        """Test creating a user with a password (backward compat)."""
        user = create_user(test_db, "newuser@example.com", "password123", "user")

        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.password_hash is not None
        assert verify_password("password123", user.password_hash)

    def test_create_admin(self, test_db: Session):
        """Test creating an admin user."""
        admin = create_user(test_db, "admin@example.com", role="admin")

        assert admin.id is not None
        assert admin.email == "admin@example.com"
        assert admin.role.value == "admin"


@pytest.mark.unit
class TestLastLogin:
    """Test last login tracking."""

    def test_update_last_login(self, test_db: Session, test_user: User):
        """Test updating last login timestamp."""
        assert test_user.last_login is None

        update_last_login(test_db, test_user)
        test_db.refresh(test_user)

        assert test_user.last_login is not None


@pytest.mark.integration
class TestAuthAPI:
    """Test the /api/v2/auth endpoints backing the SPA."""

    def test_status_anonymous_with_users(self, client, test_user):
        """An anonymous caller is reported as unauthenticated, not as a new install."""
        data = client.get("/api/v2/auth/status").json()

        assert data["authenticated"] is False
        assert data["user"] is None
        assert data["needs_registration"] is False

    def test_status_empty_install_needs_registration(self, client):
        """With no users at all, the SPA is told to show registration."""
        data = client.get("/api/v2/auth/status").json()

        assert data["authenticated"] is False
        assert data["needs_registration"] is True

    def test_status_authenticated(self, authenticated_client, test_user):
        """A valid session reports the signed-in user."""
        data = authenticated_client.get("/api/v2/auth/status").json()

        assert data["authenticated"] is True
        assert data["user"]["email"] == test_user.email
        assert data["user"]["role"] == test_user.role.value

    def test_login_sends_magic_link(self, client, test_db, test_user, mock_email_service):
        """Logging in with a known address mails a magic link."""
        from app.models import MagicLink

        response = client.post("/api/v2/auth/login", json={"email": test_user.email})

        assert response.status_code == 200
        assert response.json()["sent"] is True
        mock_email_service["send_magic_link_email"].assert_called_once()
        assert (
            test_db.query(MagicLink).filter(MagicLink.email == test_user.email).count()
            == 1
        )

    def test_login_unknown_email_does_not_leak(
        self, client, test_db, test_user, mock_email_service
    ):
        """An unknown address gets the same response, but no link is issued."""
        from app.models import MagicLink

        response = client.post(
            "/api/v2/auth/login", json={"email": "nobody@example.com"}
        )

        assert response.status_code == 200
        assert response.json()["sent"] is True
        mock_email_service["send_magic_link_email"].assert_not_called()
        assert (
            test_db.query(MagicLink)
            .filter(MagicLink.email == "nobody@example.com")
            .count()
            == 0
        )

    def test_magic_link_starts_a_session(self, client, test_db, test_user):
        """Following a valid magic link authenticates subsequent requests."""
        token = create_magic_link(test_db, test_user.email)

        response = client.get(f"/api/v2/auth/magic-link?token={token}")

        assert response.status_code == 200
        assert response.json()["user"]["email"] == test_user.email
        assert client.cookies.get("session_token")

        # The cookie the client kept is good enough to reach an authed route.
        profile = client.get("/api/v2/auth/profile")
        assert profile.status_code == 200
        assert profile.json()["email"] == test_user.email

    def test_magic_link_invalid_token_rejected(self, client, test_user):
        """A bad token neither authenticates nor 500s."""
        response = client.get("/api/v2/auth/magic-link?token=not-a-real-token")

        assert response.status_code == 400
        assert response.json()["success"] is False
        assert not client.cookies.get("session_token")

    def test_logout_clears_session(self, authenticated_client):
        """Logging out tells the browser to drop the session cookie."""
        response = authenticated_client.post("/api/v2/auth/logout")

        assert response.status_code == 200
        set_cookie = response.headers["set-cookie"]
        assert "session_token=" in set_cookie
        assert "Max-Age=0" in set_cookie

    def test_profile_requires_auth(self, client, test_user):
        """Unauthenticated profile access is rejected."""
        response = client.get("/api/v2/auth/profile", follow_redirects=False)

        assert response.status_code == 401

    def test_profile_returns_current_user(self, authenticated_client, test_user):
        """The profile route describes the signed-in user."""
        data = authenticated_client.get("/api/v2/auth/profile").json()

        assert data["id"] == test_user.id
        assert data["email"] == test_user.email
        assert data["role"] == test_user.role.value


@pytest.mark.integration
class TestRegistration:
    """First-run registration."""

    def test_register_first_user_becomes_admin(self, client, test_db):
        """The first account created on an empty install is an admin."""
        response = client.post(
            "/api/v2/auth/register", json={"email": "first@example.com"}
        )

        assert response.status_code == 200
        assert response.json()["user"]["role"] == "admin"
        assert client.cookies.get("session_token")

    def test_register_closed_once_a_user_exists(self, client, test_user):
        """Registration is not an open door once the install has an owner."""
        response = client.post(
            "/api/v2/auth/register", json={"email": "second@example.com"}
        )

        assert response.status_code == 400
        assert "error" in response.json()
