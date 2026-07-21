"""How the audiobook endpoint answers the requests podcast players actually make."""
import pytest

from app.models import Book, BookSource
from app.utils.media_types import audio_media_type


@pytest.fixture
def book(test_db):
    b = Book(
        title="T",
        asin="A1",
        source=BookSource.AUDIBLE,
        file_path="audiobooks/1.m4a",
        file_format="m4a",
        file_size=123,
    )
    test_db.add(b)
    test_db.commit()
    return b


@pytest.fixture
def b2_book(test_db, book, monkeypatch):
    """A book already uploaded to B2, with a stubbed storage service."""
    book.b2_audio_key = "audiobooks/1.m4a"
    test_db.commit()

    captured = {}

    class FakeStorage:
        def file_exists(self, key):
            return True

        def get_signed_url(self, key, content_type=None):
            captured["key"] = key
            captured["content_type"] = content_type
            return "https://b2.example/signed?x=1"

    monkeypatch.setattr("app.routers.files.get_storage_service", lambda: FakeStorage())
    return captured


def test_head_request_is_supported(client, book):
    """Players HEAD the enclosure before downloading; a 405 reads as unavailable."""
    r = client.head(f"/files/audiobooks/{book.id}.m4a", follow_redirects=False)
    assert r.status_code != 405


def test_b2_redirect_preserves_method_for_head(client, book, b2_book):
    """307, not 302, so a HEAD stays a HEAD against B2."""
    r = client.head(f"/files/audiobooks/{book.id}.m4a", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "https://b2.example/signed?x=1"


def test_b2_signed_url_forces_audio_content_type(client, book, b2_book):
    """Without this B2 serves binary/octet-stream and players reject the file."""
    client.get(f"/files/audiobooks/{book.id}.m4a", follow_redirects=False)
    assert b2_book["content_type"] == "audio/mp4"


def test_local_fallback_serves_audio_content_type(client, book, tmp_path, monkeypatch):
    from app.config import settings

    audio_dir = tmp_path / "audiobooks"
    audio_dir.mkdir()
    (audio_dir / "1.m4a").write_bytes(b"fake audio")
    monkeypatch.setattr(settings, "audiobooks_path", audio_dir)
    monkeypatch.setattr("app.routers.files.get_storage_service", lambda: None)

    r = client.get(f"/files/audiobooks/{book.id}.m4a", follow_redirects=False)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/mp4")


def test_enclosure_type_matches_what_is_served():
    """The RSS <enclosure type> and the served Content-Type come from one map."""
    assert audio_media_type("m4a") == "audio/mp4"
    assert audio_media_type("M4B") == "audio/x-m4b"
    assert audio_media_type(".mp3") == "audio/mpeg"
    assert audio_media_type(None) == "audio/x-m4b"


class FakeStorageWithBucket:
    """Storage stub whose bucket contents are explicit."""

    def __init__(self, present_keys, raise_on_check=False):
        self.present = set(present_keys)
        self.raise_on_check = raise_on_check

    def file_exists(self, key):
        if self.raise_on_check:
            raise RuntimeError("B2 unreachable")
        return key in self.present

    def get_signed_url(self, key, content_type=None):
        return f"https://b2.example/{key}"


@pytest.fixture
def local_file(book, tmp_path, monkeypatch):
    from app.config import settings

    audio_dir = tmp_path / "audiobooks"
    audio_dir.mkdir()
    (audio_dir / "1.m4a").write_bytes(b"fake audio")
    monkeypatch.setattr(settings, "audiobooks_path", audio_dir)
    return audio_dir


def test_stale_key_falls_back_to_local_instead_of_redirecting(
    client, test_db, book, local_file, monkeypatch
):
    """The reported bug: key recorded, object absent, player got a 404 from B2."""
    book.b2_audio_key = "audiobooks/1.m4a"  # old id-based scheme, not in bucket
    test_db.commit()
    monkeypatch.setattr(
        "app.routers.files.get_storage_service", lambda: FakeStorageWithBucket([])
    )

    r = client.get(f"/files/audiobooks/{book.id}.m4a", follow_redirects=False)
    assert r.status_code == 200
    assert r.content == b"fake audio"


def test_stale_key_is_cleared_so_it_gets_reuploaded(
    client, test_db, book, local_file, monkeypatch
):
    book.b2_audio_key = "audiobooks/1.m4a"
    test_db.commit()
    monkeypatch.setattr(
        "app.routers.files.get_storage_service", lambda: FakeStorageWithBucket([])
    )

    client.get(f"/files/audiobooks/{book.id}.m4a", follow_redirects=False)

    test_db.refresh(book)
    assert book.b2_audio_key is None


def test_present_key_still_redirects(client, test_db, book, monkeypatch):
    book.b2_audio_key = "audiobooks/Chaos [1].m4a"
    test_db.commit()
    monkeypatch.setattr(
        "app.routers.files.get_storage_service",
        lambda: FakeStorageWithBucket(["audiobooks/Chaos [1].m4a"]),
    )

    r = client.get(f"/files/audiobooks/{book.id}.m4a", follow_redirects=False)
    assert r.status_code == 307


def test_b2_outage_serves_locally_and_keeps_the_key(
    client, test_db, book, local_file, monkeypatch
):
    """An outage is not evidence the file is gone — the key must survive it."""
    book.b2_audio_key = "audiobooks/Chaos [1].m4a"
    test_db.commit()
    monkeypatch.setattr(
        "app.routers.files.get_storage_service",
        lambda: FakeStorageWithBucket([], raise_on_check=True),
    )

    r = client.get(f"/files/audiobooks/{book.id}.m4a", follow_redirects=False)
    assert r.status_code == 200

    test_db.refresh(book)
    assert book.b2_audio_key == "audiobooks/Chaos [1].m4a"
