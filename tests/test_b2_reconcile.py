"""The periodic sweep that drops B2 keys whose objects have vanished."""
import pytest

from app.models import Book, BookSource
from app.services.b2_upload import B2UploadService


class FakeStorage:
    def __init__(self, present_keys, raise_on_check=False):
        self.present = set(present_keys)
        self.raise_on_check = raise_on_check

    def file_exists(self, key):
        if self.raise_on_check:
            raise RuntimeError("B2 unreachable")
        return key in self.present


def make_book(db, book_id, audio_key=None, cover_key=None):
    b = Book(
        id=book_id,
        title=f"Book {book_id}",
        asin=f"A{book_id}",
        source=BookSource.AUDIBLE,
        file_path=f"audiobooks/{book_id}.m4a",
        file_format="m4a",
        b2_audio_key=audio_key,
        b2_cover_key=cover_key,
    )
    db.add(b)
    db.commit()
    return b


@pytest.fixture
def storage(monkeypatch):
    def install(fake):
        monkeypatch.setattr("app.services.b2_upload.get_storage_service", lambda: fake)
        return fake

    return install


def test_clears_key_missing_from_bucket(test_db, storage):
    """The exact reported state: an old-scheme key with no object behind it."""
    book = make_book(test_db, 1, audio_key="audiobooks/1.m4a")
    storage(FakeStorage(present_keys=[]))

    stats = B2UploadService(test_db).reconcile_keys()

    test_db.refresh(book)
    assert book.b2_audio_key is None
    assert stats["cleared"] == 1


def test_keeps_key_that_is_present(test_db, storage):
    book = make_book(test_db, 2, audio_key="audiobooks/Book 2 [2].m4a")
    storage(FakeStorage(present_keys=["audiobooks/Book 2 [2].m4a"]))

    stats = B2UploadService(test_db).reconcile_keys()

    test_db.refresh(book)
    assert book.b2_audio_key == "audiobooks/Book 2 [2].m4a"
    assert stats["cleared"] == 0


def test_outage_does_not_clear_anything(test_db, storage):
    """A network failure must never be read as 'the file is gone'."""
    book = make_book(test_db, 3, audio_key="audiobooks/Book 3 [3].m4a")
    storage(FakeStorage(present_keys=[], raise_on_check=True))

    stats = B2UploadService(test_db).reconcile_keys()

    test_db.refresh(book)
    assert book.b2_audio_key == "audiobooks/Book 3 [3].m4a"
    assert stats["cleared"] == 0
    assert stats["errors"] == 1


def test_checks_covers_too(test_db, storage):
    book = make_book(test_db, 4, audio_key="a-present", cover_key="c-missing")
    storage(FakeStorage(present_keys=["a-present"]))

    B2UploadService(test_db).reconcile_keys()

    test_db.refresh(book)
    assert book.b2_audio_key == "a-present"
    assert book.b2_cover_key is None


def test_cleared_book_becomes_pending_again(test_db, storage):
    """Clearing must feed find_pending(), or the file is never restored."""
    book = make_book(test_db, 5, audio_key="audiobooks/5.m4a")
    storage(FakeStorage(present_keys=[]))
    svc = B2UploadService(test_db)

    assert book.id not in [b.id for b in svc.find_pending()]
    svc.reconcile_keys()
    assert book.id in [b.id for b in svc.find_pending()]


def test_no_storage_configured_is_a_noop(test_db, monkeypatch):
    book = make_book(test_db, 6, audio_key="audiobooks/6.m4a")
    monkeypatch.setattr("app.services.b2_upload.get_storage_service", lambda: None)

    stats = B2UploadService(test_db).reconcile_keys()

    test_db.refresh(book)
    assert book.b2_audio_key == "audiobooks/6.m4a"
    assert stats["checked"] == 0
