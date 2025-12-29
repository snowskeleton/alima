"""Tests for admin routes."""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Invite, User, UserRole


@pytest.mark.integration
class TestAdminInvites:
    """Test admin invite management routes."""

    def test_list_invites_requires_admin(self, authenticated_client: TestClient):
        """Test that listing invites requires admin role."""
        response = authenticated_client.get("/admin/invites")
        assert response.status_code == 403

    def test_list_invites_as_admin(self, admin_client: TestClient, test_db: Session):
        """Test admin can list invites."""
        # Create a test invite
        invite = Invite(
            email="newuser@example.com",
            token="test-token-123",
            role=UserRole.USER,
            created_by=1,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        test_db.add(invite)
        test_db.commit()

        response = admin_client.get("/admin/invites")
        assert response.status_code == 200
        assert b"newuser@example.com" in response.content

    def test_send_invite_creates_invite(
        self, admin_client: TestClient, test_db: Session
    ):
        """Test sending an invite creates an invite record."""
        response = admin_client.post(
            "/admin/invites/send",
            data={
                "email": "invited@example.com",
                "role": "user",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303  # Redirect

        # Verify invite was created
        invite = (
            test_db.query(Invite)
            .filter(Invite.email == "invited@example.com")
            .first()
        )
        assert invite is not None
        assert invite.role == UserRole.USER
        assert invite.used == False

    def test_send_invite_to_existing_user_fails(
        self, admin_client: TestClient, test_user: User
    ):
        """Test sending invite to existing user fails."""
        response = admin_client.post(
            "/admin/invites/send",
            data={
                "email": test_user.email,
                "role": "user",
            },
        )
        assert response.status_code == 400

    def test_revoke_invite(self, admin_client: TestClient, test_db: Session):
        """Test revoking an unused invite."""
        # Create a test invite
        invite = Invite(
            email="revoke@example.com",
            token="revoke-token",
            role=UserRole.USER,
            created_by=1,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        test_db.add(invite)
        test_db.commit()
        test_db.refresh(invite)

        response = admin_client.delete(f"/admin/invites/{invite.id}")
        assert response.status_code == 200

        # Verify invite was deleted
        deleted_invite = test_db.query(Invite).filter(Invite.id == invite.id).first()
        assert deleted_invite is None


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
        response = admin_client.post(
            f"/admin/users/{test_user.id}/change-role",
            data={"role": "admin"},
        )
        assert response.status_code == 200

        # Verify role was changed
        test_db.refresh(test_user)
        assert test_user.role == UserRole.ADMIN

    def test_cannot_change_own_role(self, admin_client: TestClient, test_admin: User):
        """Test admin cannot change their own role."""
        response = admin_client.post(
            f"/admin/users/{test_admin.id}/change-role",
            data={"role": "user"},
        )
        assert response.status_code == 400

    def test_delete_user(
        self, admin_client: TestClient, test_user: User, test_db: Session
    ):
        """Test admin can delete a user."""
        user_id = test_user.id
        response = admin_client.delete(f"/admin/users/{user_id}")
        assert response.status_code == 200

        # Verify user was deleted
        deleted_user = test_db.query(User).filter(User.id == user_id).first()
        assert deleted_user is None

    def test_cannot_delete_own_account(
        self, admin_client: TestClient, test_admin: User
    ):
        """Test admin cannot delete their own account."""
        response = admin_client.delete(f"/admin/users/{test_admin.id}")
        assert response.status_code == 400
