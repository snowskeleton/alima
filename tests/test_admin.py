"""Tests for admin user management (/api/v2/users)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, UserRole


@pytest.mark.integration
class TestUserAdminAccess:
    """Only admins may reach user management."""

    def test_list_users_requires_admin(self, authenticated_client: TestClient):
        response = authenticated_client.get("/api/v2/users")
        assert response.status_code == 403

    def test_create_user_requires_admin(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/api/v2/users", json={"email": "nope@example.com"}
        )
        assert response.status_code == 403

    def test_list_users_requires_a_session(self, client: TestClient, test_user: User):
        """Anonymous callers are bounced to login rather than shown the list."""
        response = client.get("/api/v2/users", follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers["location"]


@pytest.mark.integration
class TestListUsers:
    """Listing accounts."""

    def test_list_returns_every_account(
        self, admin_client: TestClient, test_user: User, test_admin: User
    ):
        users = admin_client.get("/api/v2/users").json()["users"]

        emails = {u["email"] for u in users}
        assert {test_user.email, test_admin.email} <= emails

    def test_list_never_exposes_credentials(
        self, admin_client: TestClient, test_user: User
    ):
        users = admin_client.get("/api/v2/users").json()["users"]

        assert all("password_hash" not in u for u in users)

    def test_list_honours_sort_order(
        self, admin_client: TestClient, test_user: User, test_admin: User
    ):
        ascending = admin_client.get("/api/v2/users?sort=email_asc").json()["users"]
        descending = admin_client.get("/api/v2/users?sort=email_desc").json()["users"]

        emails = [u["email"] for u in ascending]
        assert emails == sorted(emails)
        assert [u["email"] for u in descending] == list(reversed(emails))


@pytest.mark.integration
class TestCreateUser:
    """Creating an account sends the new user a way in."""

    def test_create_user_creates_account_and_sends_link(
        self, admin_client: TestClient, test_db: Session, mock_email_service
    ):
        response = admin_client.post(
            "/api/v2/users", json={"email": "invited@example.com", "role": "user"}
        )

        assert response.status_code == 200
        assert response.json()["user"]["email"] == "invited@example.com"

        user = (
            test_db.query(User).filter(User.email == "invited@example.com").first()
        )
        assert user is not None
        assert user.role == UserRole.USER

        mock_email_service["send_magic_link_email"].assert_called_once()

    def test_create_user_gets_a_default_feed(
        self, admin_client: TestClient, test_db: Session
    ):
        """A new account is usable immediately: it comes with its own feed."""
        from app.models import Feed

        admin_client.post("/api/v2/users", json={"email": "feeded@example.com"})

        user = test_db.query(User).filter(User.email == "feeded@example.com").first()
        feeds = test_db.query(Feed).filter(Feed.user_id == user.id).all()
        assert len(feeds) == 1
        assert feeds[0].is_public is False

    def test_create_duplicate_email_rejected(
        self, admin_client: TestClient, test_user: User
    ):
        response = admin_client.post("/api/v2/users", json={"email": test_user.email})

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_send_login_link_to_existing_user(
        self, admin_client: TestClient, test_user: User, mock_email_service
    ):
        response = admin_client.post(
            f"/api/v2/users/{test_user.id}/send-login-link"
        )

        assert response.status_code == 200
        mock_email_service["send_magic_link_email"].assert_called_once()
        assert (
            mock_email_service["send_magic_link_email"].call_args.kwargs[
                "recipient_email"
            ]
            == test_user.email
        )


@pytest.mark.integration
class TestChangeRole:
    """Role changes."""

    def test_admin_can_promote_a_user(
        self, admin_client: TestClient, test_user: User, test_db: Session
    ):
        response = admin_client.patch(
            f"/api/v2/users/{test_user.id}", json={"role": "admin"}
        )

        assert response.status_code == 200
        test_db.refresh(test_user)
        assert test_user.role == UserRole.ADMIN

    def test_admin_cannot_demote_themselves(
        self, admin_client: TestClient, test_admin: User, test_db: Session
    ):
        """Guards against an install locking itself out of admin."""
        response = admin_client.patch(
            f"/api/v2/users/{test_admin.id}", json={"role": "user"}
        )

        assert response.status_code == 400
        test_db.refresh(test_admin)
        assert test_admin.role == UserRole.ADMIN

    def test_change_role_of_unknown_user(self, admin_client: TestClient):
        response = admin_client.patch("/api/v2/users/99999", json={"role": "admin"})
        assert response.status_code == 404

    def test_notifications_are_admin_only(
        self, admin_client: TestClient, test_user: User
    ):
        response = admin_client.patch(
            f"/api/v2/users/{test_user.id}", json={"receive_notifications": True}
        )
        assert response.status_code == 400


@pytest.mark.integration
class TestDeleteUser:
    """Account deletion."""

    def test_admin_can_delete_a_user(
        self, admin_client: TestClient, test_user: User, test_db: Session
    ):
        user_id = test_user.id

        response = admin_client.delete(f"/api/v2/users/{user_id}")

        assert response.status_code == 200
        assert test_db.query(User).filter(User.id == user_id).first() is None

    def test_admin_cannot_delete_themselves(
        self, admin_client: TestClient, test_admin: User, test_db: Session
    ):
        response = admin_client.delete(f"/api/v2/users/{test_admin.id}")

        assert response.status_code == 400
        assert test_db.query(User).filter(User.id == test_admin.id).first() is not None

    def test_delete_unknown_user(self, admin_client: TestClient):
        response = admin_client.delete("/api/v2/users/99999")
        assert response.status_code == 404
