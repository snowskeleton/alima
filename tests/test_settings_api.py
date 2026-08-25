"""Contract tests for /api/v2/settings.

Most of the risk in this router is in the update path, which is not a plain
write: it masks secrets on the way out, treats a masked value on the way back in
as "leave it alone", normalises booleans and endpoints, and silently ignores
keys it does not recognise. Each of those is a place where a settings save can
quietly destroy a credential, so they are asserted individually.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.routers.api_v2.settings import BOOL_KEYS, SECRET_KEYS, SETTING_KEYS
from app.services.settings_service import SettingsService


@pytest.fixture(autouse=True)
def _clear_cache():
    """Settings are read through a process-wide cache; isolate the tests."""
    from app.utils.settings_cache import clear_settings_cache

    clear_settings_cache()
    yield
    clear_settings_cache()


class TestReadSettings:
    def test_requires_admin(self, authenticated_client: TestClient):
        assert authenticated_client.get("/api/v2/settings").status_code == 403

    def test_returns_every_known_key(self, admin_client: TestClient):
        settings = admin_client.get("/api/v2/settings").json()["settings"]
        assert set(settings) == set(SETTING_KEYS)

    @pytest.mark.parametrize("key", sorted(SECRET_KEYS))
    def test_stored_secrets_are_masked_never_sent(
        self, admin_client: TestClient, test_db: Session, key: str
    ):
        SettingsService(test_db).set(key=key, value="hunter2", category="general")

        settings = admin_client.get("/api/v2/settings").json()["settings"]
        assert settings[key] == "********"
        assert "hunter2" not in admin_client.get("/api/v2/settings").text

    @pytest.mark.parametrize("key", sorted(SECRET_KEYS))
    def test_unset_secrets_come_back_empty_not_masked(
        self, admin_client: TestClient, key: str
    ):
        """An empty string means "nothing stored"; a mask would imply there is."""
        settings = admin_client.get("/api/v2/settings").json()["settings"]
        assert settings[key] == ""

    @pytest.mark.parametrize(
        "stored,expected",
        [
            ("true", "true"),
            ("True", "true"),
            ("1", "true"),
            ("yes", "true"),
            ("on", "true"),
            ("  TRUE  ", "true"),
            ("false", "false"),
            ("False", "false"),
            ("0", "false"),
            ("", "false"),
            ("anything else", "false"),
        ],
    )
    def test_booleans_are_normalised_on_the_way_out(
        self, admin_client: TestClient, test_db: Session, stored, expected
    ):
        """Env-configured values arrive as "True"; the GUI writes "true".

        Without normalising, an env-configured setting renders as off, and
        saving the form would genuinely turn it off.
        """
        SettingsService(test_db).set(
            key="b2_enabled", value=stored, category="storage"
        )
        settings = admin_client.get("/api/v2/settings").json()["settings"]
        assert settings["b2_enabled"] == expected


class TestUpdateSettings:
    def test_requires_admin(self, authenticated_client: TestClient):
        response = authenticated_client.put(
            "/api/v2/settings", json={"app_name": "Hacked"}
        )
        assert response.status_code == 403

    def test_writes_a_plain_value(
        self, admin_client: TestClient, test_db: Session
    ):
        admin_client.put("/api/v2/settings", json={"app_name": "My Library"})
        assert SettingsService(test_db).get("app_name") == "My Library"

    def test_ignores_keys_it_does_not_know(
        self, admin_client: TestClient, test_db: Session
    ):
        response = admin_client.put(
            "/api/v2/settings", json={"not_a_setting": "x", "app_name": "Kept"}
        )
        assert response.status_code == 200
        assert SettingsService(test_db).get("not_a_setting") is None
        assert SettingsService(test_db).get("app_name") == "Kept"

    def test_whitespace_is_stripped(
        self, admin_client: TestClient, test_db: Session
    ):
        """Pasted credentials and hostnames routinely carry whitespace, which
        boto3 and SMTP both reject unhelpfully."""
        admin_client.put("/api/v2/settings", json={"smtp_host": "  mail.example.com  "})
        assert SettingsService(test_db).get("smtp_host") == "mail.example.com"

    def test_empty_string_becomes_null(
        self, admin_client: TestClient, test_db: Session
    ):
        service = SettingsService(test_db)
        service.set(key="smtp_host", value="mail.example.com", category="email")

        admin_client.put("/api/v2/settings", json={"smtp_host": ""})
        assert SettingsService(test_db).get("smtp_host") in (None, "")


class TestSecretHandling:
    """The mask round-trip is the dangerous path: the client reads back
    "********" and posts the whole form, so the update handler must not take
    that literally and overwrite the real credential."""

    @pytest.mark.parametrize("key", sorted(SECRET_KEYS))
    def test_posting_the_mask_back_leaves_the_secret_intact(
        self, admin_client: TestClient, test_db: Session, key: str
    ):
        SettingsService(test_db).set(key=key, value="real-secret", category="general")

        admin_client.put("/api/v2/settings", json={key: "********"})

        assert SettingsService(test_db).get(key) == "real-secret", (
            "saving the settings form must not overwrite the stored secret with "
            "the mask the client was shown"
        )

    @pytest.mark.parametrize("key", sorted(SECRET_KEYS))
    def test_posting_an_empty_secret_leaves_it_intact(
        self, admin_client: TestClient, test_db: Session, key: str
    ):
        SettingsService(test_db).set(key=key, value="real-secret", category="general")

        admin_client.put("/api/v2/settings", json={key: ""})

        assert SettingsService(test_db).get(key) == "real-secret"

    @pytest.mark.parametrize("key", sorted(SECRET_KEYS))
    def test_a_genuinely_new_secret_is_written(
        self, admin_client: TestClient, test_db: Session, key: str
    ):
        SettingsService(test_db).set(key=key, value="old", category="general")

        admin_client.put("/api/v2/settings", json={key: "brand-new-secret"})

        assert SettingsService(test_db).get(key) == "brand-new-secret"


class TestEndpointNormalisation:
    @pytest.mark.parametrize(
        "pasted",
        [
            "s3.us-west-002.backblazeb2.com",
            "  s3.us-west-002.backblazeb2.com  ",
            "https://s3.us-west-002.backblazeb2.com",
        ],
    )
    def test_endpoint_gains_a_scheme(
        self, admin_client: TestClient, test_db: Session, pasted: str
    ):
        """Backblaze displays the endpoint without a scheme; boto3 requires one."""
        admin_client.put("/api/v2/settings", json={"b2_endpoint_url": pasted})
        stored = SettingsService(test_db).get("b2_endpoint_url")
        assert stored.startswith("https://"), stored
        assert " " not in stored


class TestCacheInvalidation:
    def test_an_update_is_visible_immediately(
        self, admin_client: TestClient, test_db: Session
    ):
        """Settings are read through an in-memory cache. Without clearing it,
        a saved value would not take effect until the process restarted."""
        admin_client.put("/api/v2/settings", json={"app_name": "First"})
        assert admin_client.get("/api/v2/settings").json()["settings"]["app_name"] == "First"

        admin_client.put("/api/v2/settings", json={"app_name": "Second"})
        assert admin_client.get("/api/v2/settings").json()["settings"]["app_name"] == "Second"


class TestTestEmail:
    def test_requires_a_recipient(self, admin_client: TestClient):
        response = admin_client.post("/api/v2/settings/test-email", json={})
        assert response.status_code == 400

    def test_requires_admin(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/api/v2/settings/test-email", json={"recipient_email": "a@b.c"}
        )
        assert response.status_code == 403


class TestDefaultCover:
    def test_requires_admin(self, authenticated_client: TestClient):
        assert (
            authenticated_client.delete("/api/v2/settings/default-cover").status_code
            == 403
        )

    def test_removing_an_unset_cover_is_not_an_error(self, admin_client: TestClient):
        assert admin_client.delete("/api/v2/settings/default-cover").status_code == 200
