"""Tests for recovering downloads wedged in DOWNLOADING/DECRYPTING."""

import datetime

import pytest
from sqlalchemy.orm import Session

from app.models import (
    AudibleAccount,
    Book,
    BookSource,
    DownloadQueue,
    DownloadStatus,
    DownloadType,
)
from app.routers.api_v2.downloads import _build_stats
from app.services.book_download import BookDownloadService, is_entry_stale


@pytest.fixture
def account(test_db: Session) -> AudibleAccount:
    account = AudibleAccount(
        username="reader@example.com",
        auth_file_path="reader.json",
        activation_bytes="deadbeef",
        marketplace="us",
    )
    test_db.add(account)
    test_db.commit()
    return account


@pytest.fixture
def book(test_db: Session, account: AudibleAccount) -> Book:
    book = Book(
        title="A Stuck Book",
        author="Author",
        asin="B00STUCK01",
        audible_account_id=account.id,
        source=BookSource.AUDIBLE,
    )
    test_db.add(book)
    test_db.commit()
    return book


def _queue(
    test_db: Session,
    book: Book,
    status: DownloadStatus,
    *,
    minutes_ago: int = 0,
    attempts: int = 1,
) -> DownloadQueue:
    entry = DownloadQueue(
        book_id=book.id,
        audible_account_id=book.audible_account_id,
        asin=book.asin,
        download_type=DownloadType.BOOK,
        status=status,
        attempts=attempts,
        started_at=datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(minutes=minutes_ago),
    )
    test_db.add(entry)
    test_db.commit()
    return entry


class TestStaleDetection:
    def test_fresh_in_flight_entry_is_not_stale(self, test_db, book):
        entry = _queue(test_db, book, DownloadStatus.DECRYPTING, minutes_ago=1)
        assert is_entry_stale(entry) is False

    def test_long_running_entry_is_stale(self, test_db, book):
        entry = _queue(test_db, book, DownloadStatus.DECRYPTING, minutes_ago=600)
        assert is_entry_stale(entry) is True

    def test_in_flight_without_started_at_is_stale(self, test_db, book):
        entry = _queue(test_db, book, DownloadStatus.DOWNLOADING)
        entry.started_at = None
        test_db.commit()
        assert is_entry_stale(entry) is True

    def test_pending_and_terminal_statuses_are_never_stale(self, test_db, book):
        for status in (
            DownloadStatus.PENDING,
            DownloadStatus.COMPLETED,
            DownloadStatus.FAILED,
        ):
            entry = _queue(test_db, book, status, minutes_ago=6000)
            assert is_entry_stale(entry) is False


class TestReapStaleEntries:
    def test_stale_entry_is_requeued(self, test_db, book):
        entry = _queue(test_db, book, DownloadStatus.DECRYPTING, minutes_ago=600)

        stats = BookDownloadService(test_db).reap_stale_entries()

        assert stats["requeued"] == 1
        assert entry.status == DownloadStatus.PENDING
        assert entry.started_at is None
        assert "decrypting" in entry.error_message

    def test_fresh_entry_is_left_alone(self, test_db, book):
        entry = _queue(test_db, book, DownloadStatus.DOWNLOADING, minutes_ago=1)

        stats = BookDownloadService(test_db).reap_stale_entries()

        assert stats == {"checked": 1, "requeued": 0, "failed": 0}
        assert entry.status == DownloadStatus.DOWNLOADING

    def test_startup_sweep_reaps_regardless_of_age(self, test_db, book):
        """No download worker survives a restart, so age is irrelevant then."""
        entry = _queue(test_db, book, DownloadStatus.DOWNLOADING, minutes_ago=1)

        stats = BookDownloadService(test_db).reap_stale_entries(ignore_age=True)

        assert stats["requeued"] == 1
        assert entry.status == DownloadStatus.PENDING

    def test_exhausted_attempts_fail_instead_of_looping(self, test_db, book):
        entry = _queue(
            test_db, book, DownloadStatus.DECRYPTING, minutes_ago=600, attempts=3
        )

        stats = BookDownloadService(test_db).reap_stale_entries()

        assert stats["failed"] == 1
        assert entry.status == DownloadStatus.FAILED
        assert "after 3 attempts" in entry.error_message


class TestQueueStats:
    """The downloads page polls these, so they must be both right and cheap."""

    def test_buckets_every_status_plus_stalled(self, test_db, book):
        _queue(test_db, book, DownloadStatus.PENDING)
        _queue(test_db, book, DownloadStatus.DOWNLOADING, minutes_ago=1)
        _queue(test_db, book, DownloadStatus.DECRYPTING, minutes_ago=600)
        _queue(test_db, book, DownloadStatus.COMPLETED)
        _queue(test_db, book, DownloadStatus.FAILED)

        stats = _build_stats(test_db)

        assert stats["total"] == 5
        assert stats["pending"] == 1
        assert stats["downloading"] == 1
        assert stats["decrypting"] == 1
        assert stats["completed"] == 1
        assert stats["failed"] == 1
        # downloading + decrypting, distinct from the per-status buckets
        assert stats["in_flight"] == 2
        assert stats["stalled"] == 1

    def test_unread_is_counted_separately_from_status(self, test_db, book):
        read_entry = _queue(test_db, book, DownloadStatus.COMPLETED)
        read_entry.read = True
        _queue(test_db, book, DownloadStatus.COMPLETED)
        test_db.commit()

        assert _build_stats(test_db)["unread"] == 1

    def test_empty_queue_reports_zeroes_not_missing_keys(self, test_db):
        stats = _build_stats(test_db)

        assert stats["total"] == 0
        for key in ("pending", "downloading", "decrypting", "completed", "failed",
                    "in_flight", "stalled", "unread"):
            assert stats[key] == 0, key


class TestManualRequeue:
    def test_stuck_entry_is_reclaimed_not_refused(self, test_db, book):
        """The reported bug: a stuck entry made the book permanently unqueueable."""
        entry = _queue(test_db, book, DownloadStatus.DECRYPTING, minutes_ago=600)

        result = BookDownloadService(test_db).download_book_now(book.id)

        assert result["requeued"] is True
        assert result["status"] == DownloadStatus.PENDING.value
        assert entry.status == DownloadStatus.PENDING
        assert entry.attempts == 0

    def test_genuinely_active_entry_is_still_reported_as_queued(self, test_db, book):
        _queue(test_db, book, DownloadStatus.DOWNLOADING, minutes_ago=1)

        result = BookDownloadService(test_db).download_book_now(book.id)

        assert "already queued" in result["message"]
        assert result.get("requeued") is None

    def test_force_reclaims_an_active_entry(self, test_db, book):
        entry = _queue(test_db, book, DownloadStatus.DOWNLOADING, minutes_ago=1)

        result = BookDownloadService(test_db).download_book_now(book.id, force=True)

        assert result["requeued"] is True
        assert entry.status == DownloadStatus.PENDING

    def test_requeue_does_not_create_a_duplicate_entry(self, test_db, book):
        _queue(test_db, book, DownloadStatus.DECRYPTING, minutes_ago=600)

        BookDownloadService(test_db).download_book_now(book.id)

        assert test_db.query(DownloadQueue).filter(
            DownloadQueue.book_id == book.id
        ).count() == 1
