"""Deterministic regression tests for input-validation crashes.

Every case here was found by the Schemathesis run in test_openapi_fuzz.py. That
test generates inputs randomly, so it is good at *finding* this class of bug and
bad at *guarding* against it -- a future regression might survive several runs
before an unlucky seed catches it. These pin the specific inputs.

The shared shape of all of them: a client-supplied value reached a parser or an
enum constructor without being validated, so a bad request produced a 500
instead of a 4xx.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, UserRole


@pytest.fixture
def admin_json_client(client: TestClient, test_admin: User):
    """Admin client that also carries the JSON Accept header."""
    from app.auth import create_access_token

    token = create_access_token(
        data={"sub": test_admin.email, "user_id": test_admin.id}
    )
    client.cookies.set("session_token", token)
    client.headers.update({"Accept": "application/json"})
    return client


class TestEnumParameters:
    """Enum values taken from request bodies used to raise ValueError -> 500."""

    def test_unknown_feed_type_is_rejected(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/api/v2/feeds", data={"name": "n", "feed_type": "not-a-feed-type"}
        )
        assert response.status_code == 400
        assert "feed_type" in response.json()["detail"]

    @pytest.mark.parametrize("feed_type", ["smart", "manual"])
    def test_valid_feed_types_still_work(
        self, authenticated_client: TestClient, feed_type: str
    ):
        """The guard must not have narrowed what the endpoint accepts."""
        response = authenticated_client.post(
            "/api/v2/feeds", data={"name": f"feed-{feed_type}", "feed_type": feed_type}
        )
        assert response.status_code == 200, response.text

    def test_unknown_role_on_create_is_rejected(self, admin_json_client: TestClient):
        response = admin_json_client.post(
            "/api/v2/users", json={"email": "new@example.com", "role": "superuser"}
        )
        assert response.status_code == 400
        assert "role" in response.json()["detail"]

    def test_unknown_role_on_patch_is_rejected(
        self, admin_json_client: TestClient, test_user: User
    ):
        response = admin_json_client.patch(
            f"/api/v2/users/{test_user.id}", json={"role": "superuser"}
        )
        assert response.status_code == 400

    def test_valid_role_change_still_works(
        self, admin_json_client: TestClient, test_user: User
    ):
        response = admin_json_client.patch(
            f"/api/v2/users/{test_user.id}", json={"role": "admin"}
        )
        assert response.status_code == 200
        assert response.json()["role"] == "admin"


class TestEnumQueryParameters:
    """Enum-valued *query* parameters compared straight against enum columns.

    This class is dialect-sensitive in a way the others are not. SQLite does not
    enforce enum types, so an invalid value silently matched no rows and the
    endpoint returned 200; PostgreSQL raises DataError and the same request is a
    500. It was caught only by the PostgreSQL CI job.

    These assertions hold on both dialects, because the value is now validated
    before it reaches the query.
    """

    @pytest.mark.parametrize("value", ["null", "nonsense", "AUDIBLE!", "0"])
    def test_invalid_book_source_is_rejected(
        self, authenticated_client: TestClient, value: str
    ):
        response = authenticated_client.get(f"/api/v2/books?source={value}")
        assert response.status_code == 400, (
            f"source={value!r} produced {response.status_code}; on PostgreSQL an "
            "unvalidated value is a DataError and therefore a 500"
        )

    @pytest.mark.parametrize("value", ["audible", "imported"])
    def test_valid_book_source_still_filters(
        self, authenticated_client: TestClient, make_book, value: str
    ):
        from app.models import BookSource

        make_book(source=BookSource(value))
        make_book(source=BookSource("imported" if value == "audible" else "audible"))

        body = authenticated_client.get(f"/api/v2/books?source={value}").json()
        assert body["total"] == 1
        assert body["books"][0]["source"] == value

    def test_empty_source_means_no_filter(
        self, authenticated_client: TestClient, make_book
    ):
        make_book()
        response = authenticated_client.get("/api/v2/books?source=")
        assert response.status_code == 200
        assert response.json()["total"] == 1


class TestDateParameters:
    """`date_from`/`date_to` are free-form strings parsed with strptime."""

    @pytest.mark.parametrize("param", ["date_from", "date_to"])
    @pytest.mark.parametrize("value", ["null", "nope", "2024-13-45", "2024/01/01"])
    def test_unparseable_date_is_rejected(
        self, admin_json_client: TestClient, param: str, value: str
    ):
        response = admin_json_client.get(f"/api/v2/downloads?{param}={value}")
        assert response.status_code in (400, 422), (
            f"{param}={value!r} produced {response.status_code}"
        )

    @pytest.mark.parametrize("param", ["date_from", "date_to"])
    def test_valid_date_is_accepted(self, admin_json_client: TestClient, param: str):
        response = admin_json_client.get(f"/api/v2/downloads?{param}=2024-01-01")
        assert response.status_code == 200, response.text

    @pytest.mark.parametrize("param", ["date_from", "date_to"])
    def test_empty_date_means_no_filter(
        self, admin_json_client: TestClient, param: str
    ):
        """An empty value is falsy and skips the filter entirely, which is fine.

        Asserted explicitly so the "reject unparseable dates" guard above is not
        later tightened into rejecting the empty string the UI sends when its
        date picker is cleared.
        """
        response = admin_json_client.get(f"/api/v2/downloads?{param}=")
        assert response.status_code == 200


class TestOversizedIdentifiers:
    """Path ids wider than a 64-bit integer overflowed the database driver.

    Without a declared upper bound these reached the driver and raised
    OverflowError instead of matching no rows.
    """

    HUGE = 2**63  # one past the top of a signed 64-bit integer

    # Method matters: users, downloads and accounts have no GET route, so a GET
    # never reached them at all -- it fell through to the SPA catch-all, and the
    # assertion passed against that instead of against the endpoint.
    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/v2/books/{id}"),
            ("GET", "/api/v2/feeds/{id}"),
            ("GET", "/files/audiobooks/{id}.m4b"),
            ("DELETE", "/api/v2/users/{id}"),
            ("DELETE", "/api/v2/downloads/{id}"),
            ("DELETE", "/api/v2/accounts/{id}"),
            ("PATCH", "/api/v2/books/{id}"),
        ],
    )
    def test_oversized_id_is_rejected(
        self, admin_json_client: TestClient, method: str, path: str
    ):
        response = admin_json_client.request(
            method, path.format(id=self.HUGE), json={} if method == "PATCH" else None
        )
        assert response.status_code < 500, (
            f"{method} {path} returned {response.status_code} for an id wider "
            "than 64 bits"
        )
        # Specifically a validation rejection, not an incidental 404/405 that
        # would let a genuine overflow slip back in unnoticed.
        assert response.status_code == 422, (
            f"{method} {path} returned {response.status_code}; the declared "
            "bound on DatabaseId should make this a 422"
        )

    def test_zero_and_negative_ids_are_rejected(self, admin_json_client: TestClient):
        for bad in (0, -1):
            response = admin_json_client.get(f"/api/v2/books/{bad}")
            assert response.status_code < 500

    def test_ordinary_id_still_resolves(self, admin_json_client: TestClient):
        """The bound must not have broken normal lookups."""
        response = admin_json_client.get("/api/v2/books/1")
        assert response.status_code == 404  # no such book, but handled


class TestFileUploads:
    """Uploaded bytes reached parsers that assumed well-formed input."""

    def test_auth_file_that_is_not_a_json_object_is_rejected(
        self, admin_json_client: TestClient
    ):
        """json.loads("1") returns an int, which has no .get()."""
        response = admin_json_client.post(
            "/api/v2/accounts",
            data={"username": "u", "marketplace": "us"},
            files={"auth_file": ("a.json", io.BytesIO(b"1"), "application/json")},
        )
        assert response.status_code == 400

    def test_auth_file_with_non_utf8_bytes_is_rejected(
        self, admin_json_client: TestClient
    ):
        """json.loads decodes as UTF-8 first, so binary raises before parsing."""
        response = admin_json_client.post(
            "/api/v2/accounts",
            data={"username": "u", "marketplace": "us"},
            files={
                "auth_file": ("a.json", io.BytesIO(b"\x80\x81\x82"), "application/json")
            },
        )
        assert response.status_code == 400

    def test_cover_upload_that_is_not_an_image_is_rejected(
        self, authenticated_client: TestClient
    ):
        """Pillow raises UnidentifiedImageError on arbitrary bytes."""
        response = authenticated_client.post(
            "/api/v2/feeds",
            data={"name": "feed", "feed_type": "manual"},
            files={"cover_image": ("c.jpg", io.BytesIO(b"not an image"), "image/jpeg")},
        )
        assert response.status_code == 400
        assert "image" in response.json()["detail"].lower()


class TestCoverServing:
    """A directory under covers/ exists but cannot be served."""

    def test_directory_path_is_a_miss_not_a_crash(
        self, client: TestClient, tmp_path, monkeypatch
    ):
        from app.config import settings

        covers = tmp_path / "covers"
        (covers / "subdir").mkdir(parents=True)
        monkeypatch.setattr(settings, "covers_path", covers)

        response = client.get("/files/covers/subdir", follow_redirects=False)
        assert response.status_code < 500, (
            "Handing a directory to FileResponse raises RuntimeError; it should "
            "be treated as a miss."
        )


def test_gif_covers_are_served_as_gif(client: TestClient, tmp_path, monkeypatch):
    """The media-type table mapped .gif to image/webp."""
    from app.config import settings

    covers = tmp_path / "covers"
    covers.mkdir(parents=True)
    # Smallest valid GIF89a; content doesn't matter, only the extension mapping.
    (covers / "x.gif").write_bytes(
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
        b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
        b"\x00\x02\x02D\x01\x00;"
    )
    monkeypatch.setattr(settings, "covers_path", covers)

    response = client.get("/files/covers/x.gif")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/gif"
