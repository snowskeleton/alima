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
from app.services.book_download import (
    BookDownloadService,
    entry_eta_seconds,
    is_entry_stale,
)


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
    progress_minutes_ago: int | None = None,
    bytes_downloaded: int | None = None,
) -> DownloadQueue:
    now = datetime.datetime.now(datetime.timezone.utc)
    entry = DownloadQueue(
        book_id=book.id,
        audible_account_id=book.audible_account_id,
        asin=book.asin,
        download_type=DownloadType.BOOK,
        status=status,
        attempts=attempts,
        started_at=now - datetime.timedelta(minutes=minutes_ago),
        bytes_downloaded=bytes_downloaded,
        progress_at=(
            now - datetime.timedelta(minutes=progress_minutes_ago)
            if progress_minutes_ago is not None
            else None
        ),
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


class TestProgressKeepsEntriesAlive:
    """
    The whole point of byte tracking: a slow transfer is not a stalled one.
    Staleness is judged on when the byte count last moved, not on how long the
    download has been running.
    """

    def test_long_download_still_reporting_progress_is_not_stale(self, test_db, book):
        # Ten hours in — far past any age threshold — but it moved bytes a
        # minute ago, so something is clearly still happening.
        entry = _queue(
            test_db,
            book,
            DownloadStatus.DOWNLOADING,
            minutes_ago=600,
            progress_minutes_ago=1,
            bytes_downloaded=900 * 1024 * 1024,
        )
        assert is_entry_stale(entry) is False

    def test_long_decrypt_still_reporting_progress_is_not_stale(self, test_db, book):
        entry = _queue(
            test_db,
            book,
            DownloadStatus.DECRYPTING,
            minutes_ago=600,
            progress_minutes_ago=2,
            bytes_downloaded=400 * 1024 * 1024,
        )
        assert is_entry_stale(entry) is False

    def test_recently_started_but_frozen_entry_is_stale(self, test_db, book):
        # Started 20 minutes ago and hasn't moved a byte in 20 minutes. Under
        # the old age-only rule this was fine; it is exactly the case we want
        # caught now.
        entry = _queue(
            test_db,
            book,
            DownloadStatus.DOWNLOADING,
            minutes_ago=20,
            progress_minutes_ago=20,
            bytes_downloaded=35 * 1024 * 1024,
        )
        assert is_entry_stale(entry) is True

    def test_entry_without_progress_yet_falls_back_to_started_at(self, test_db, book):
        """An entry that hasn't reported its first chunk is judged on age."""
        fresh = _queue(test_db, book, DownloadStatus.DOWNLOADING, minutes_ago=1)
        assert is_entry_stale(fresh) is False

        frozen = _queue(test_db, book, DownloadStatus.DOWNLOADING, minutes_ago=600)
        assert is_entry_stale(frozen) is True

    def test_stalled_entry_reports_how_far_it_got(self, test_db, book):
        entry = _queue(
            test_db,
            book,
            DownloadStatus.DOWNLOADING,
            minutes_ago=60,
            progress_minutes_ago=30,
            bytes_downloaded=35 * 1024 * 1024,
        )

        BookDownloadService(test_db).reap_stale_entries()

        assert "35 MB" in entry.error_message
        assert "idle 30m" in entry.error_message

    def test_requeue_clears_progress(self, test_db, book):
        """Otherwise the retry starts out looking 35 MB into the transfer."""
        entry = _queue(
            test_db,
            book,
            DownloadStatus.DOWNLOADING,
            minutes_ago=60,
            progress_minutes_ago=30,
            bytes_downloaded=35 * 1024 * 1024,
        )

        BookDownloadService(test_db).reap_stale_entries()

        assert entry.status == DownloadStatus.PENDING
        assert entry.bytes_downloaded is None
        assert entry.progress_at is None


class TestEta:
    """
    A rough ETA from the average rate so far. Accuracy isn't the point; not
    lying when there's nothing to go on is.
    """

    def _in_flight(self, test_db, book, *, done, total, seconds_elapsed, status=None):
        now = datetime.datetime.now(datetime.timezone.utc)
        entry = _queue(
            test_db,
            book,
            status or DownloadStatus.DOWNLOADING,
            bytes_downloaded=done,
            progress_minutes_ago=0,
        )
        entry.total_bytes = total
        entry.phase_started_at = now - datetime.timedelta(seconds=seconds_elapsed)
        test_db.commit()
        return entry

    def test_half_done_estimates_the_elapsed_time_again(self, test_db, book):
        entry = self._in_flight(
            test_db, book, done=50_000_000, total=100_000_000, seconds_elapsed=60
        )
        # 50 MB in 60s => ~0.83 MB/s, 50 MB remaining => ~60s.
        assert entry_eta_seconds(entry) == pytest.approx(60, abs=2)

    def test_quarter_done_estimates_three_times_elapsed(self, test_db, book):
        entry = self._in_flight(
            test_db, book, done=25_000_000, total=100_000_000, seconds_elapsed=30
        )
        assert entry_eta_seconds(entry) == pytest.approx(90, abs=3)

    def test_no_eta_without_a_known_total(self, test_db, book):
        entry = self._in_flight(
            test_db, book, done=10_000_000, total=None, seconds_elapsed=60
        )
        assert entry_eta_seconds(entry) is None

    def test_no_eta_before_any_bytes(self, test_db, book):
        entry = self._in_flight(
            test_db, book, done=0, total=100_000_000, seconds_elapsed=60
        )
        assert entry_eta_seconds(entry) is None

    def test_no_eta_in_the_first_few_seconds(self, test_db, book):
        """Too little elapsed time to estimate a rate from."""
        entry = self._in_flight(
            test_db, book, done=1_000_000, total=100_000_000, seconds_elapsed=1
        )
        assert entry_eta_seconds(entry) is None

    def test_no_eta_once_complete(self, test_db, book):
        entry = self._in_flight(
            test_db, book, done=100_000_000, total=100_000_000, seconds_elapsed=60
        )
        assert entry_eta_seconds(entry) is None

    def test_no_eta_for_terminal_statuses(self, test_db, book):
        entry = self._in_flight(
            test_db, book, done=50_000_000, total=100_000_000, seconds_elapsed=60
        )
        entry.status = DownloadStatus.COMPLETED
        test_db.commit()
        assert entry_eta_seconds(entry) is None

    def test_decrypt_eta_ignores_time_spent_downloading(self, test_db, book):
        """
        phase_started_at exists for exactly this: measuring the decrypt rate
        from started_at would fold in the download and wildly overestimate.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        entry = _queue(
            test_db,
            book,
            DownloadStatus.DECRYPTING,
            minutes_ago=60,  # the download began an hour ago
            bytes_downloaded=50_000_000,
            progress_minutes_ago=0,
        )
        entry.total_bytes = 100_000_000
        entry.phase_started_at = now - datetime.timedelta(seconds=60)
        test_db.commit()

        # 60s for half of it, not 3600s.
        assert entry_eta_seconds(entry) == pytest.approx(60, abs=2)


class TestRestartAccounting:
    def test_startup_reclaim_refunds_the_attempt(self, test_db, book):
        """
        A process that died holding an entry never got to try it. Charging the
        attempt anyway let an OOM loop burn all three in minutes and
        permanently fail a book that was downloading fine.
        """
        entry = _queue(test_db, book, DownloadStatus.DOWNLOADING, attempts=1)

        BookDownloadService(test_db).reap_stale_entries(ignore_age=True)

        assert entry.status == DownloadStatus.PENDING
        assert entry.attempts == 0

    def test_repeated_restarts_do_not_exhaust_attempts(self, test_db, book):
        entry = _queue(test_db, book, DownloadStatus.DOWNLOADING, attempts=1)
        service = BookDownloadService(test_db)

        for _ in range(5):
            service.reap_stale_entries(ignore_age=True)
            assert entry.status == DownloadStatus.PENDING
            # Simulate the next worker picking it up and dying again.
            entry.status = DownloadStatus.DOWNLOADING
            entry.attempts += 1
            entry.started_at = datetime.datetime.now(datetime.timezone.utc)
            test_db.commit()

        assert entry.status == DownloadStatus.DOWNLOADING

    def test_genuine_failures_still_exhaust_attempts(self, test_db, book):
        """The refund is only for restarts — real stalls still give up."""
        entry = _queue(
            test_db,
            book,
            DownloadStatus.DECRYPTING,
            minutes_ago=600,
            progress_minutes_ago=600,
            attempts=3,
        )

        BookDownloadService(test_db).reap_stale_entries()

        assert entry.status == DownloadStatus.FAILED


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
