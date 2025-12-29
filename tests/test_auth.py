"""Tests for authentication functionality."""

import pytest
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    get_password_hash,
    update_last_login,
    verify_password,
    verify_token,
)
from app.models import User


@pytest.mark.unit
class TestPasswordHashing:
    """Test password hashing functions."""

    def test_password_hash(self):
        """Test password hashing."""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt prefix

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
class TestUserAuthentication:
    """Test user authentication."""

    def test_authenticate_user_success(self, test_db: Session, test_user: User):
        """Test successful user authentication."""
        user = authenticate_user(test_db, "test@example.com", "testpassword")

        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email

    def test_authenticate_user_wrong_password(self, test_db: Session, test_user: User):
        """Test authentication with wrong password."""
        user = authenticate_user(test_db, "test@example.com", "wrongpassword")

        assert user is None

    def test_authenticate_user_nonexistent(self, test_db: Session):
        """Test authentication with nonexistent user."""
        user = authenticate_user(test_db, "nonexistent@example.com", "password")

        assert user is None


@pytest.mark.unit
class TestUserCreation:
    """Test user creation."""

    def test_create_user(self, test_db: Session):
        """Test creating a new user."""
        user = create_user(test_db, "newuser@example.com", "password123", "user")

        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.role.value == "user"
        assert verify_password("password123", user.password_hash)

    def test_create_admin(self, test_db: Session):
        """Test creating an admin user."""
        admin = create_user(test_db, "admin@example.com", "adminpass", "admin")

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

    def test_login_page(self, client):
        """Test login page is accessible."""
        from fastapi.testclient import TestClient
        response = client.get("/auth/login")
        assert response.status_code == 200
        assert b"Sign In" in response.content

    def test_login_redirects_if_already_logged_in(self, authenticated_client):
        """Test login page redirects if already logged in."""
        from fastapi.testclient import TestClient
        response = authenticated_client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/library"

    def test_login_success(self, client, test_user):
        """Test successful login."""
        from fastapi.testclient import TestClient
        response = client.post(
            "/auth/login",
            data={
                "email": "test@example.com",
                "password": "testpassword",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "session_token" in response.cookies

    def test_login_wrong_password(self, client, test_user):
        """Test login with wrong password."""
        from fastapi.testclient import TestClient
        response = client.post(
            "/auth/login",
            data={
                "email": "test@example.com",
                "password": "wrongpassword",
            },
        )
        assert response.status_code == 401

    def test_logout(self, authenticated_client):
        """Test logout."""
        from fastapi.testclient import TestClient
        response = authenticated_client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login"

    def test_accept_invite_page(self, client, test_db):
        """Test accept invite page with valid token."""
        from datetime import datetime, timedelta
        from app.models import Invite, UserRole

        # Create a test invite
        invite = Invite(
            email="newinvite@example.com",
            token="valid-invite-token",
            role=UserRole.USER,
            created_by=1,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        test_db.add(invite)
        test_db.commit()

        response = client.get("/auth/accept-invite?token=valid-invite-token")
        assert response.status_code == 200
        assert b"newinvite@example.com" in response.content

    def test_accept_invite_invalid_token(self, client):
        """Test accept invite page with invalid token."""
        response = client.get("/auth/accept-invite?token=invalid-token")
        assert response.status_code == 404

    def test_accept_invite_creates_user(self, client, test_db):
        """Test accepting invite creates user account."""
        from datetime import datetime, timedelta
        from app.models import Invite, User, UserRole

        # Create a test invite
        invite = Invite(
            email="newaccount@example.com",
            token="new-account-token",
            role=UserRole.USER,
            created_by=1,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        test_db.add(invite)
        test_db.commit()

        response = client.post(
            "/auth/accept-invite",
            data={
                "token": "new-account-token",
                "password": "newpassword123",
                "password_confirm": "newpassword123",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "session_token" in response.cookies

        # Verify user was created
        user = test_db.query(User).filter(User.email == "newaccount@example.com").first()
        assert user is not None
        assert verify_password("newpassword123", user.password_hash)

        # Verify invite was marked as used
        test_db.refresh(invite)
        assert invite.used is True

    def test_profile_page_requires_auth(self, client):
        """Test profile page requires authentication."""
        response = client.get("/auth/profile")
        assert response.status_code == 401

    def test_profile_page_authenticated(self, authenticated_client, test_user):
        """Test profile page with authenticated user."""
        response = authenticated_client.get("/auth/profile")
        assert response.status_code == 200
        assert test_user.email.encode() in response.content
