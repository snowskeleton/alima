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
class TestAuthRoutes:
    """Test authentication routes."""

    def test_login_page(self, client, test_user):
        """Test login page is accessible."""
        response = client.get("/auth/login")
        assert response.status_code == 200
        assert b"Send me a login link" in response.content

    def test_login_redirects_if_already_logged_in(self, authenticated_client):
        """Test login page redirects if already logged in."""
        response = authenticated_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/library"

    def _get_csrf_token(self, client, url="/auth/login"):
        """Helper to get a CSRF token by visiting a page first."""
        response = client.get(url)
        csrf_cookie = response.cookies.get("alima_csrf", "")
        return csrf_cookie

    def test_login_shows_check_email(self, client, test_user):
        """Test submitting login shows check-email page."""
        csrf = self._get_csrf_token(client)
        response = client.post(
            "/auth/login",
            data={
                "email": "test@example.com",
            },
            headers={"x-csrf-token": csrf},
        )
        assert response.status_code == 200
        assert b"Check your email" in response.content

    def test_login_nonexistent_email_still_shows_check_email(self, client, test_user):
        """Test submitting nonexistent email still shows check-email (prevents enumeration)."""
        csrf = self._get_csrf_token(client)
        response = client.post(
            "/auth/login",
            data={
                "email": "nonexistent@example.com",
            },
            headers={"x-csrf-token": csrf},
        )
        assert response.status_code == 200
        assert b"Check your email" in response.content

    def test_magic_link_login(self, client, test_db, test_user):
        """Test magic link creates session."""
        token = create_magic_link(test_db, test_user.email)

        response = client.get(
            f"/auth/magic-link?token={token}",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "session_token" in response.cookies

    def test_magic_link_expired(self, client, test_user):
        """Test expired/invalid magic link shows error page."""
        response = client.get("/auth/magic-link?token=invalid-token")
        assert response.status_code == 200
        assert b"expired" in response.content.lower()

    def test_logout(self, authenticated_client):
        """Test logout."""
        response = authenticated_client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login"

    def test_profile_page_requires_auth(self, client, test_user):
        """Test profile page requires authentication (redirects to login)."""
        response = client.get("/auth/profile", follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers["location"]

    def test_profile_page_authenticated(self, authenticated_client, test_user):
        """Test profile page with authenticated user."""
        response = authenticated_client.get("/auth/profile")
        assert response.status_code == 200
        assert test_user.email.encode() in response.content
