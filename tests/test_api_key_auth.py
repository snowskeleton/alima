"""API keys authenticate the same endpoints a browser session does."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Feed, FeedType, User


def bearer(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


class TestApiKeyAuthentication:
    """An API key stands in for the session cookie on normal endpoints."""

    def test_api_key_can_read_books(self, client: TestClient, user_api_key: str):
        response = client.get("/api/v2/books", headers=bearer(user_api_key))
        assert response.status_code == 200

    def test_api_key_identifies_its_owner(
        self, client: TestClient, user_api_key: str, test_user: User
    ):
        response = client.get("/api/v2/auth/profile", headers=bearer(user_api_key))
        assert response.status_code == 200
        assert response.json()["email"] == test_user.email

    def test_missing_credentials_are_rejected(self, client: TestClient, test_user: User):
        response = client.get("/api/v2/books", follow_redirects=False)
        assert response.status_code == 401

    def test_unknown_key_is_rejected(self, client: TestClient, test_user: User):
        response = client.get("/api/v2/books", headers=bearer("not-a-real-key"))
        assert response.status_code == 401

    def test_bad_key_does_not_fall_back_to_a_session(
        self, authenticated_client: TestClient
    ):
        """A wrong bearer token fails even when a valid cookie is also present."""
        response = authenticated_client.get("/api/v2/books", headers=bearer("bogus"))
        assert response.status_code == 401


class TestApiKeyRoles:
    """Keys inherit the role of the user that owns them."""

    def test_non_admin_key_cannot_list_users(
        self, client: TestClient, user_api_key: str
    ):
        response = client.get("/api/v2/users", headers=bearer(user_api_key))
        assert response.status_code == 403

    def test_admin_key_can_list_users(self, client: TestClient, admin_api_key: str):
        response = client.get("/api/v2/users", headers=bearer(admin_api_key))
        assert response.status_code == 200


class TestApiKeyMutations:
    """Write and delete endpoints work over API key auth, not just cookies."""

    def test_api_key_can_create_and_delete_a_feed(
        self, client: TestClient, user_api_key: str, test_db: Session
    ):
        created = client.post(
            "/api/v2/feeds",
            headers=bearer(user_api_key),
            data={"name": "Key Made This", "feed_type": FeedType.MANUAL.value},
        )
        assert created.status_code == 200
        feed_id = created.json()["id"]

        deleted = client.delete(
            f"/api/v2/feeds/{feed_id}", headers=bearer(user_api_key)
        )
        assert deleted.status_code == 200
        assert test_db.query(Feed).filter(Feed.id == feed_id).first() is None


class TestApiDiscovery:
    """The server describes its own interface without authentication."""

    def test_api_index_points_at_the_schema(self, client: TestClient):
        response = client.get("/api")
        assert response.status_code == 200
        body = response.json()
        assert body["openapi"].endswith("/openapi.json")
        assert body["authentication"]["scheme"] == "bearer"

    def test_openapi_schema_is_served(self, client: TestClient):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert "ApiKeyBearer" in response.json()["components"]["securitySchemes"]

    def test_protected_routes_declare_the_bearer_scheme(self, client: TestClient):
        schema = client.get("/openapi.json").json()
        delete_feed = schema["paths"]["/api/v2/feeds/{feed_id}"]["delete"]
        assert {"ApiKeyBearer": []} in delete_feed["security"]

    def test_interactive_docs_are_available(self, client: TestClient):
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200


class TestApiKeyExpiry:
    """Keys can carry an expiry; keys without one keep working forever."""

    def test_expired_key_is_rejected(
        self, client: TestClient, test_db: Session, test_user: User
    ):
        from tests.conftest import issue_api_key

        key = issue_api_key(
            test_db,
            test_user,
            "stale",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        response = client.get("/api/v2/books", headers=bearer(key))
        assert response.status_code == 401
        assert response.json()["detail"] == "Expired API key"

    def test_unexpired_key_still_works(
        self, client: TestClient, test_db: Session, test_user: User
    ):
        from tests.conftest import issue_api_key

        key = issue_api_key(
            test_db,
            test_user,
            "fresh",
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
        assert client.get("/api/v2/books", headers=bearer(key)).status_code == 200

    def test_key_without_expiry_never_expires(
        self, client: TestClient, user_api_key: str
    ):
        """Existing keys carry expires_at = NULL and must keep authenticating."""
        assert client.get("/api/v2/books", headers=bearer(user_api_key)).status_code == 200

    def test_created_key_defaults_to_no_expiry(
        self, admin_client: TestClient, test_db: Session
    ):
        response = admin_client.post("/api/v2/api-keys", json={"name": "no expiry"})
        assert response.status_code == 200
        assert response.json()["expires_at"] is None

    def test_created_key_can_request_an_expiry(self, admin_client: TestClient):
        response = admin_client.post(
            "/api/v2/api-keys", json={"name": "temp", "expires_in_days": 30}
        )
        assert response.status_code == 200
        assert response.json()["expires_at"] is not None

    def test_nonsense_expiry_is_rejected(self, admin_client: TestClient):
        response = admin_client.post(
            "/api/v2/api-keys", json={"name": "bad", "expires_in_days": 0}
        )
        assert response.status_code == 400


class TestApiKeyUsageTracking:
    """last_used_at answers 'is this key still in use?'."""

    def test_new_key_reports_never_used(
        self, admin_client: TestClient, test_admin: User
    ):
        admin_client.post("/api/v2/api-keys", json={"name": "unused"})
        listed = admin_client.get("/api/v2/api-keys").json()["api_keys"]
        assert listed[0]["last_used_at"] is None

    def test_using_a_key_stamps_last_used(
        self, client: TestClient, test_db: Session, test_admin: User
    ):
        from app.models import ApiKey
        from tests.conftest import issue_api_key

        key = issue_api_key(test_db, test_admin, "worker")
        record = test_db.query(ApiKey).filter(ApiKey.name == "worker").one()
        assert record.last_used_at is None

        assert client.get("/api/v2/books", headers=bearer(key)).status_code == 200

        test_db.expire_all()
        assert record.last_used_at is not None

    def test_recent_use_is_not_rewritten_on_every_request(
        self, client: TestClient, test_db: Session, test_admin: User
    ):
        """A busy key gets one write, not one per request."""
        from app.models import ApiKey
        from tests.conftest import issue_api_key

        key = issue_api_key(test_db, test_admin, "busy")
        client.get("/api/v2/books", headers=bearer(key))
        test_db.expire_all()
        first = test_db.query(ApiKey).filter(ApiKey.name == "busy").one().last_used_at

        client.get("/api/v2/books", headers=bearer(key))
        test_db.expire_all()
        second = test_db.query(ApiKey).filter(ApiKey.name == "busy").one().last_used_at

        assert first == second

    def test_rejected_key_is_not_stamped(
        self, client: TestClient, test_db: Session, test_user: User
    ):
        from app.models import ApiKey
        from tests.conftest import issue_api_key

        key = issue_api_key(
            test_db,
            test_user,
            "expired",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        client.get("/api/v2/books", headers=bearer(key))

        test_db.expire_all()
        assert test_db.query(ApiKey).filter(ApiKey.name == "expired").one().last_used_at is None


class TestKeyManagementIsSessionOnly:
    """A key cannot manage keys: no self-issuing, no self-enumeration."""

    def test_admin_key_cannot_mint_another_key(
        self, client: TestClient, admin_api_key: str
    ):
        response = client.post(
            "/api/v2/api-keys",
            headers=bearer(admin_api_key),
            json={"name": "escalation"},
        )
        assert response.status_code == 401

    def test_admin_key_cannot_list_keys(self, client: TestClient, admin_api_key: str):
        response = client.get("/api/v2/api-keys", headers=bearer(admin_api_key))
        assert response.status_code == 401

    def test_admin_key_cannot_revoke_keys(self, client: TestClient, admin_api_key: str):
        response = client.delete("/api/v2/api-keys/1", headers=bearer(admin_api_key))
        assert response.status_code == 401

    def test_admin_session_still_manages_keys(self, admin_client: TestClient):
        created = admin_client.post("/api/v2/api-keys", json={"name": "from session"})
        assert created.status_code == 200

        listed = admin_client.get("/api/v2/api-keys")
        assert listed.status_code == 200

        key_id = created.json()["key_id"]
        assert admin_client.delete(f"/api/v2/api-keys/{key_id}").status_code == 200

    def test_key_management_still_requires_admin(self, authenticated_client: TestClient):
        """A non-admin session is refused too - session auth is not a bypass."""
        response = authenticated_client.get("/api/v2/api-keys")
        assert response.status_code == 403


class TestOptionalAuthEndpoints:
    """Optional auth means "no credentials", not "wrong credentials"."""

    def _public_feed_slug(self, db: Session, user: User) -> str:
        from app.models import Feed

        feed = Feed(
            user_id=user.id,
            name="Public Feed",
            feed_type=FeedType.MANUAL,
            slug="public-feed",
            is_public=True,
        )
        db.add(feed)
        db.commit()
        return feed.slug

    def test_anonymous_access_still_works(
        self, client: TestClient, test_db: Session, test_user: User
    ):
        slug = self._public_feed_slug(test_db, test_user)
        assert client.get(f"/api/v2/feeds/by-slug/{slug}").status_code == 200

    def test_valid_key_is_accepted(
        self, client: TestClient, test_db: Session, test_user: User, user_api_key: str
    ):
        slug = self._public_feed_slug(test_db, test_user)
        response = client.get(
            f"/api/v2/feeds/by-slug/{slug}", headers=bearer(user_api_key)
        )
        assert response.status_code == 200

    def test_bad_key_does_not_silently_fall_back_to_a_session(
        self, authenticated_client: TestClient, test_db: Session, test_user: User
    ):
        """A revoked key must not quietly act as whoever holds the cookie."""
        slug = self._public_feed_slug(test_db, test_user)
        response = authenticated_client.get(
            f"/api/v2/feeds/by-slug/{slug}", headers=bearer("revoked")
        )
        assert response.status_code == 401

    def test_expired_key_is_reported_as_expired(
        self, client: TestClient, test_db: Session, test_user: User
    ):
        from tests.conftest import issue_api_key

        slug = self._public_feed_slug(test_db, test_user)
        key = issue_api_key(
            test_db, test_user, "old", expires_at=datetime.utcnow() - timedelta(days=1)
        )
        response = client.get(f"/api/v2/feeds/by-slug/{slug}", headers=bearer(key))
        assert response.status_code == 401
        assert response.json()["detail"] == "Expired API key"


class TestUsageTrackingIsolation:
    """Recording a key's use must not disturb the request's own session."""

    def test_stamp_is_skipped_when_the_session_has_pending_work(
        self, test_db: Session, test_admin: User
    ):
        """Bookkeeping never commits - or rolls back - unrelated pending changes."""
        from app.dependencies import _record_key_use
        from app.models import ApiKey
        from tests.conftest import issue_api_key

        issue_api_key(test_db, test_admin, "tracked")
        record = test_db.query(ApiKey).filter(ApiKey.name == "tracked").one()

        # Unrelated pending change on the same session.
        test_admin.email = "pending@example.com"
        assert test_db.dirty

        _record_key_use(test_db, record)

        # The edit is still pending: neither committed nor discarded.
        assert test_db.dirty
        assert record.last_used_at is None

    def test_stamp_lands_on_a_clean_session(
        self, test_db: Session, test_admin: User
    ):
        from app.dependencies import _record_key_use
        from app.models import ApiKey
        from tests.conftest import issue_api_key

        issue_api_key(test_db, test_admin, "clean")
        record = test_db.query(ApiKey).filter(ApiKey.name == "clean").one()

        _record_key_use(test_db, record)

        assert record.last_used_at is not None
