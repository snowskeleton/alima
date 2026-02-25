"""Tests for admin routes."""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, UserRole


def _get_csrf(client, url="/admin/users"):
    """Helper to get a CSRF token by visiting a page."""
    response = client.get(url)
    return response.cookies.get("alima_csrf", "")


@pytest.mark.integration
class TestAdminInvites:
    """Test admin invite/user creation routes."""

    def test_list_invites_requires_admin(self, authenticated_client: TestClient):
        """Test that listing invites requires admin role."""
        response = authenticated_client.get("/admin/invites")
        assert response.status_code == 403

    def test_send_invite_creates_user(
        self, admin_client: TestClient, test_db: Session
    ):
        """Test sending an invite creates a user account."""
        csrf = _get_csrf(admin_client)
        response = admin_client.post(
            "/admin/invites/send",
            data={
                "email": "invited@example.com",
                "role": "user",
            },
            headers={"x-csrf-token": csrf},
            follow_redirects=False,
        )
        assert response.status_code == 303  # Redirect

        # Verify user was created
        user = (
            test_db.query(User)
            .filter(User.email == "invited@example.com")
            .first()
        )
        assert user is not None
        assert user.role == UserRole.USER

    def test_send_invite_to_existing_user_fails(
        self, admin_client: TestClient, test_user: User
    ):
        """Test sending invite to existing user shows error."""
        csrf = _get_csrf(admin_client)
        response = admin_client.post(
            "/admin/invites/send",
            data={
                "email": test_user.email,
                "role": "user",
            },
            headers={"x-csrf-token": csrf},
            follow_redirects=False,
        )
        # Should redirect back with error flash message
        assert response.status_code == 303


@pytest.mark.integration
class TestAdminUsers:
    """Test admin user management routes."""

    def test_list_users_requires_admin(self, authenticated_client: TestClient):
        """Test that listing users requires admin role."""
        response = authenticated_client.get("/admin/users")
        assert response.status_code == 403

    def test_list_users_as_admin(
        self, admin_client: TestClient, test_user: User, test_admin: User
    ):
        """Test admin can list all users."""
        response = admin_client.get("/admin/users")
        assert response.status_code == 200
        assert b"test@example.com" in response.content
        assert b"admin@example.com" in response.content

    def test_change_user_role(
        self, admin_client: TestClient, test_user: User, test_db: Session
    ):
        """Test admin can change user role."""
        csrf = _get_csrf(admin_client)
        response = admin_client.post(
            f"/admin/users/{test_user.id}/change-role",
            data={"role": "admin"},
            headers={"x-csrf-token": csrf},
        )
        assert response.status_code == 200

        # Verify role was changed
        test_db.refresh(test_user)
        assert test_user.role == UserRole.ADMIN

    def test_cannot_change_own_role(self, admin_client: TestClient, test_admin: User):
        """Test admin cannot change their own role."""
        csrf = _get_csrf(admin_client)
        response = admin_client.post(
            f"/admin/users/{test_admin.id}/change-role",
            data={"role": "user"},
            headers={"x-csrf-token": csrf},
        )
        data = response.json()
        assert "error" in data

    def test_delete_user(
        self, admin_client: TestClient, test_user: User, test_db: Session
    ):
        """Test admin can delete a user."""
        csrf = _get_csrf(admin_client)
        user_id = test_user.id
        response = admin_client.delete(
            f"/admin/users/{user_id}",
            headers={"x-csrf-token": csrf},
        )
        assert response.status_code == 200

        # Verify user was deleted
        deleted_user = test_db.query(User).filter(User.id == user_id).first()
        assert deleted_user is None

    def test_cannot_delete_own_account(
        self, admin_client: TestClient, test_admin: User
    ):
        """Test admin cannot delete their own account."""
        csrf = _get_csrf(admin_client)
        response = admin_client.delete(
            f"/admin/users/{test_admin.id}",
            headers={"x-csrf-token": csrf},
        )
        data = response.json()
        assert "error" in data
