"""Contract tests for /api/v2/downloads.

The download queue is admin-only and entirely stateful, so these tests are about
state transitions: what a retry resets, what a bulk action actually touched, and
whether a missing entry is reported as missing.

That last one is not hypothetical. Three of these handlers used to
`return {"error": ...}, 404`, which FastAPI serialises as a two-element JSON
array with HTTP 200 -- so the client read "entry not found" as success.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import DownloadQueue, DownloadStatus


@pytest.fixture
def account(make_account):
    return make_account()


@pytest.fixture
def entry(make_queue_entry, make_book, account):
    return make_queue_entry(make_book(), account)


class TestListDownloads:
    def test_requires_admin(self, authenticated_client: TestClient):
        assert authenticated_client.get("/api/v2/downloads").status_code == 403

    def test_returns_entries_and_stats(self, admin_client: TestClient, entry):
        body = admin_client.get("/api/v2/downloads").json()
        assert "entries" in body
        assert "stats" in body

    def test_read_filter_partitions_the_queue(
        self, admin_client: TestClient, make_queue_entry, make_book, account
    ):
        make_queue_entry(make_book(), account, read=False)
        make_queue_entry(make_book(), account, read=True)

        unread = admin_client.get("/api/v2/downloads?read_status=unread").json()
        assert all(e["read"] is False for e in unread["entries"])

    def test_status_filter_accepts_either_case(
        self, admin_client: TestClient, make_queue_entry, make_book, account
    ):
        """The API emits lowercase values while SQLAlchemy persists uppercase
        names, so clients reasonably send either."""
        make_queue_entry(make_book(), account, status=DownloadStatus.FAILED)

        lower = admin_client.get("/api/v2/downloads?status=failed&read_status=all")
        upper = admin_client.get("/api/v2/downloads?status=FAILED&read_status=all")
        assert len(lower.json()["entries"]) == len(upper.json()["entries"]) == 1

    def test_unknown_status_filter_is_not_an_error(self, admin_client: TestClient):
        assert admin_client.get("/api/v2/downloads?status=nonsense").status_code == 200

    def test_book_id_filter(
        self, admin_client: TestClient, make_queue_entry, make_book, account
    ):
        wanted = make_book()
        make_queue_entry(wanted, account)
        make_queue_entry(make_book(), account)

        body = admin_client.get(
            f"/api/v2/downloads?book_id={wanted.id}&read_status=all"
        ).json()
        assert [e["book_id"] for e in body["entries"]] == [wanted.id]

    def test_search_matches_the_book_title(
        self, admin_client: TestClient, make_queue_entry, make_book, account
    ):
        make_queue_entry(make_book(title="Findable Title"), account)
        make_queue_entry(make_book(title="Other"), account)

        body = admin_client.get(
            "/api/v2/downloads?search=Findable&read_status=all"
        ).json()
        assert len(body["entries"]) == 1

    def test_entry_shape_includes_the_joined_book(
        self, admin_client: TestClient, make_queue_entry, make_book, account
    ):
        make_queue_entry(make_book(title="Joined", author="Writer"), account)
        entry = admin_client.get("/api/v2/downloads?read_status=all").json()["entries"][0]
        assert entry["book_title"] == "Joined"
        assert entry["book_author"] == "Writer"
        assert entry["account_username"] == account.username


class TestRetry:
    def test_resets_the_entry_to_pending(
        self, admin_client: TestClient, test_db: Session, make_queue_entry, make_book, account
    ):
        failed = make_queue_entry(
            make_book(),
            account,
            status=DownloadStatus.FAILED,
            error_message="disk full",
            attempts=3,
            started_at=datetime.utcnow() - timedelta(hours=2),
        )

        assert (
            admin_client.post(f"/api/v2/downloads/{failed.id}/retry").status_code == 200
        )

        test_db.refresh(failed)
        assert failed.status == DownloadStatus.PENDING
        assert failed.error_message is None
        assert failed.attempts == 0
        # started_at must be cleared, or the entry looks stale the instant it
        # goes back in flight and the stale-reaper picks it straight back up.
        assert failed.started_at is None

    def test_missing_entry_is_a_real_404(self, admin_client: TestClient):
        response = admin_client.post("/api/v2/downloads/999999/retry")
        assert response.status_code == 404, (
            "returning a (body, status) tuple does not set the status code; the "
            "client saw HTTP 200 and a JSON array"
        )
        assert isinstance(response.json(), dict)

    def test_requires_admin(self, authenticated_client: TestClient, entry):
        assert (
            authenticated_client.post(
                f"/api/v2/downloads/{entry.id}/retry"
            ).status_code
            == 403
        )


class TestRemove:
    def test_deletes_the_entry(
        self, admin_client: TestClient, test_db: Session, entry
    ):
        entry_id = entry.id
        assert admin_client.delete(f"/api/v2/downloads/{entry_id}").status_code == 200
        assert (
            test_db.query(DownloadQueue).filter(DownloadQueue.id == entry_id).first()
            is None
        )

    def test_missing_entry_is_a_real_404(self, admin_client: TestClient):
        response = admin_client.delete("/api/v2/downloads/999999")
        assert response.status_code == 404
        assert isinstance(response.json(), dict)

    def test_requires_admin(self, authenticated_client: TestClient, entry):
        assert (
            authenticated_client.delete(f"/api/v2/downloads/{entry.id}").status_code
            == 403
        )


class TestMarkRead:
    def test_marking_read_stamps_a_time(
        self, admin_client: TestClient, test_db: Session, entry
    ):
        admin_client.patch(f"/api/v2/downloads/{entry.id}", json={"read": True})
        test_db.refresh(entry)
        assert entry.read is True
        assert entry.read_at is not None

    def test_marking_unread_clears_the_time(
        self, admin_client: TestClient, test_db: Session, make_queue_entry, make_book, account
    ):
        e = make_queue_entry(
            make_book(), account, read=True, read_at=datetime.now(timezone.utc)
        )
        admin_client.patch(f"/api/v2/downloads/{e.id}", json={"read": False})
        test_db.refresh(e)
        assert e.read is False
        assert e.read_at is None

    def test_missing_entry_is_a_real_404(self, admin_client: TestClient):
        response = admin_client.patch("/api/v2/downloads/999999", json={"read": True})
        assert response.status_code == 404
        assert isinstance(response.json(), dict)


class TestBulkActions:
    def test_mark_read_affects_every_named_entry(
        self, admin_client: TestClient, test_db: Session, make_queue_entry, make_book, account
    ):
        entries = [make_queue_entry(make_book(), account) for _ in range(3)]
        ids = [e.id for e in entries]

        body = admin_client.post(
            "/api/v2/downloads/bulk", json={"action": "mark_read", "entry_ids": ids}
        ).json()
        assert body["affected"] == 3

        for e in entries:
            test_db.refresh(e)
            assert e.read is True

    def test_remove_deletes_them(
        self, admin_client: TestClient, test_db: Session, make_queue_entry, make_book, account
    ):
        ids = [make_queue_entry(make_book(), account).id for _ in range(2)]
        admin_client.post(
            "/api/v2/downloads/bulk", json={"action": "remove", "entry_ids": ids}
        )
        assert (
            test_db.query(DownloadQueue).filter(DownloadQueue.id.in_(ids)).count() == 0
        )

    def test_retry_resets_them(
        self, admin_client: TestClient, test_db: Session, make_queue_entry, make_book, account
    ):
        e = make_queue_entry(
            make_book(), account, status=DownloadStatus.FAILED, attempts=5
        )
        admin_client.post(
            "/api/v2/downloads/bulk", json={"action": "retry", "entry_ids": [e.id]}
        )
        test_db.refresh(e)
        assert e.status == DownloadStatus.PENDING
        assert e.attempts == 0

    def test_empty_list_is_a_no_op(self, admin_client: TestClient):
        body = admin_client.post(
            "/api/v2/downloads/bulk", json={"action": "remove", "entry_ids": []}
        ).json()
        assert body["affected"] == 0

    def test_affected_count_excludes_unknown_ids(
        self, admin_client: TestClient, entry
    ):
        """`affected` is len(entries), so unknown ids must not inflate it."""
        body = admin_client.post(
            "/api/v2/downloads/bulk",
            json={"action": "mark_read", "entry_ids": [entry.id, 999999]},
        ).json()
        assert body["affected"] == 1

    def test_unknown_action_changes_nothing(
        self, admin_client: TestClient, test_db: Session, entry
    ):
        """No action branch matches, so the entry must be left alone."""
        admin_client.post(
            "/api/v2/downloads/bulk",
            json={"action": "explode", "entry_ids": [entry.id]},
        )
        test_db.refresh(entry)
        assert entry.read is False
        assert (
            test_db.query(DownloadQueue).filter(DownloadQueue.id == entry.id).first()
            is not None
        )

    def test_requires_admin(self, authenticated_client: TestClient, entry):
        response = authenticated_client.post(
            "/api/v2/downloads/bulk",
            json={"action": "mark_read", "entry_ids": [entry.id]},
        )
        assert response.status_code == 403
