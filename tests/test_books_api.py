"""Contract tests for /api/v2/books.

Covers the listing filters, the bulk action dispatcher, and the per-book
mutations. The emphasis is on the branches that are easy to get wrong and hard
to notice: filter combinations that silently return everything, bulk actions
that report a success count they didn't earn, and the admin/non-admin split.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Book, BookSource, UserRole


@pytest.fixture
def library(make_book):
    """A small library spanning every state the list filters care about."""
    return {
        "downloaded": make_book(
            title="Downloaded Book",
            author="Ann Author",
            series="The Series",
            file_path="audiobooks/downloaded.m4b",
            downloaded_at=datetime.utcnow(),
        ),
        "pending": make_book(
            title="Pending Book",
            author="Bob Barker",
            download_enabled=True,
            download_unavailable=False,
        ),
        "disabled": make_book(
            title="Disabled Book",
            author="Cy Coder",
            download_enabled=False,
        ),
        "unavailable": make_book(
            title="Unavailable Book",
            author="Dee Dev",
            download_unavailable=True,
        ),
    }


class TestListBooks:
    def test_lists_everything_by_default(
        self, authenticated_client: TestClient, library
    ):
        body = authenticated_client.get("/api/v2/books").json()
        assert body["total"] == 4
        assert len(body["books"]) == 4

    @pytest.mark.parametrize(
        "status_filter,expected_title",
        [
            ("downloaded", "Downloaded Book"),
            ("pending", "Pending Book"),
            ("disabled", "Disabled Book"),
            ("unavailable", "Unavailable Book"),
        ],
    )
    def test_status_filter_selects_exactly_one(
        self, authenticated_client: TestClient, library, status_filter, expected_title
    ):
        body = authenticated_client.get(
            f"/api/v2/books?status={status_filter}"
        ).json()
        titles = [b["title"] for b in body["books"]]
        assert titles == [expected_title], (
            f"status={status_filter} returned {titles}"
        )

    def test_unknown_status_filter_does_not_silently_filter(
        self, authenticated_client: TestClient, library
    ):
        """An unrecognised status falls through every branch and returns all.

        Asserted so the behaviour is a decision rather than an accident: if this
        is ever changed to reject unknown values, this test should be updated
        deliberately.
        """
        body = authenticated_client.get("/api/v2/books?status=nonsense").json()
        assert body["total"] == 4

    @pytest.mark.parametrize("field", ["title", "author", "series"])
    def test_search_matches_each_indexed_field(
        self, authenticated_client: TestClient, library, field
    ):
        needle = {"title": "Downloaded", "author": "Ann", "series": "Series"}[field]
        body = authenticated_client.get(f"/api/v2/books?search={needle}").json()
        assert body["total"] == 1
        assert body["books"][0]["title"] == "Downloaded Book"

    def test_search_is_case_insensitive(
        self, authenticated_client: TestClient, library
    ):
        body = authenticated_client.get("/api/v2/books?search=dOwNlOaDeD").json()
        assert body["total"] == 1

    def test_series_filter_partitions_the_library(
        self, authenticated_client: TestClient, library
    ):
        with_series = authenticated_client.get("/api/v2/books?series_filter=series")
        standalone = authenticated_client.get(
            "/api/v2/books?series_filter=standalone"
        )
        assert with_series.json()["total"] == 1
        assert standalone.json()["total"] == 3

    def test_pagination_reports_total_not_page_size(
        self, authenticated_client: TestClient, library
    ):
        """`total` must be the unpaginated count, or the UI's pager breaks."""
        body = authenticated_client.get("/api/v2/books?limit=2&offset=0").json()
        assert len(body["books"]) == 2
        assert body["total"] == 4
        assert body["limit"] == 2
        assert body["offset"] == 0

    def test_pagination_offset_advances(
        self, authenticated_client: TestClient, library
    ):
        first = authenticated_client.get("/api/v2/books?limit=2&offset=0").json()
        second = authenticated_client.get("/api/v2/books?limit=2&offset=2").json()
        first_ids = {b["id"] for b in first["books"]}
        second_ids = {b["id"] for b in second["books"]}
        assert not (first_ids & second_ids), "pages overlap"

    def test_limit_is_capped(self, authenticated_client: TestClient, library):
        assert authenticated_client.get("/api/v2/books?limit=201").status_code == 422

    def test_negative_offset_is_rejected(
        self, authenticated_client: TestClient, library
    ):
        assert authenticated_client.get("/api/v2/books?offset=-1").status_code == 422

    @pytest.mark.parametrize("order", ["asc", "desc"])
    def test_sort_order_reverses_results(
        self, authenticated_client: TestClient, library, order
    ):
        body = authenticated_client.get(
            f"/api/v2/books?sort=title&order={order}"
        ).json()
        titles = [b["title"] for b in body["books"]]
        assert titles == sorted(titles, reverse=(order == "desc"))

    def test_unknown_sort_column_falls_back(
        self, authenticated_client: TestClient, library
    ):
        """getattr(Book, sort, added_at) must not explode on a bad column."""
        response = authenticated_client.get("/api/v2/books?sort=not_a_column")
        assert response.status_code == 200
        assert response.json()["total"] == 4


class TestGetBook:
    def test_returns_full_detail(self, authenticated_client: TestClient, test_book):
        body = authenticated_client.get(f"/api/v2/books/{test_book.id}").json()
        assert body["id"] == test_book.id
        assert body["title"] == test_book.title

    def test_missing_book_is_404(self, authenticated_client: TestClient):
        assert authenticated_client.get("/api/v2/books/999999").status_code == 404


class TestBulkActions:
    def test_rejects_unknown_action(
        self, authenticated_client: TestClient, test_book
    ):
        response = authenticated_client.post(
            "/api/v2/books/bulk",
            json={"action": "launch_missiles", "book_ids": [test_book.id]},
        )
        assert response.status_code == 400

    def test_delete_requires_admin(
        self, authenticated_client: TestClient, test_book
    ):
        response = authenticated_client.post(
            "/api/v2/books/bulk",
            json={"action": "delete", "book_ids": [test_book.id]},
        )
        assert response.status_code == 403

    def test_admin_can_bulk_delete(
        self, admin_client: TestClient, test_db: Session, make_book
    ):
        books = [make_book(), make_book()]
        ids = [b.id for b in books]

        response = admin_client.post(
            "/api/v2/books/bulk", json={"action": "delete", "book_ids": ids}
        )
        assert response.status_code == 200
        assert response.json()["affected"] == 2
        assert test_db.query(Book).filter(Book.id.in_(ids)).count() == 0

    def test_enable_download_skips_already_downloaded(
        self, authenticated_client: TestClient, test_db: Session, make_book
    ):
        """A downloaded book has nothing to enable, so it must not be counted."""
        downloaded = make_book(file_path="audiobooks/x.m4b", download_enabled=False)
        pending = make_book(download_enabled=False)

        response = authenticated_client.post(
            "/api/v2/books/bulk",
            json={
                "action": "enable_download",
                "book_ids": [downloaded.id, pending.id],
            },
        )
        assert response.json()["affected"] == 1, (
            "the already-downloaded book should not count toward affected"
        )

        test_db.refresh(downloaded)
        test_db.refresh(pending)
        assert downloaded.download_enabled is False
        assert pending.download_enabled is True

    def test_disable_download_skips_already_downloaded(
        self, authenticated_client: TestClient, test_db: Session, make_book
    ):
        downloaded = make_book(file_path="audiobooks/x.m4b", download_enabled=True)
        pending = make_book(download_enabled=True)

        response = authenticated_client.post(
            "/api/v2/books/bulk",
            json={
                "action": "disable_download",
                "book_ids": [downloaded.id, pending.id],
            },
        )
        assert response.json()["affected"] == 1

        test_db.refresh(pending)
        assert pending.download_enabled is False

    def test_unknown_ids_are_ignored_not_fatal(
        self, authenticated_client: TestClient, test_book
    ):
        response = authenticated_client.post(
            "/api/v2/books/bulk",
            json={"action": "enable_download", "book_ids": [test_book.id, 999999]},
        )
        assert response.status_code == 200
        assert response.json()["affected"] == 1

    def test_empty_id_list_is_a_no_op(self, authenticated_client: TestClient):
        response = authenticated_client.post(
            "/api/v2/books/bulk", json={"action": "enable_download", "book_ids": []}
        )
        assert response.status_code == 200
        assert response.json()["affected"] == 0


class TestMetadataOverrides:
    def test_update_requires_admin(
        self, authenticated_client: TestClient, test_book
    ):
        response = authenticated_client.put(
            f"/api/v2/books/{test_book.id}/metadata", json={"title": "New"}
        )
        assert response.status_code == 403

    def test_admin_sets_overrides(
        self, admin_client: TestClient, test_db: Session, test_book
    ):
        response = admin_client.put(
            f"/api/v2/books/{test_book.id}/metadata",
            json={"title": "Corrected Title", "author": "Corrected Author"},
        )
        assert response.status_code == 200

        test_db.refresh(test_book)
        assert test_book.metadata_override == {
            "title": "Corrected Title",
            "author": "Corrected Author",
        }

    def test_empty_values_are_dropped_not_stored(
        self, admin_client: TestClient, test_db: Session, test_book
    ):
        """Blank fields from the edit form must not persist as empty overrides."""
        admin_client.put(
            f"/api/v2/books/{test_book.id}/metadata",
            json={"title": "Kept", "author": "", "narrator": None},
        )
        test_db.refresh(test_book)
        assert test_book.metadata_override == {"title": "Kept"}

    def test_all_empty_clears_the_override_entirely(
        self, admin_client: TestClient, test_db: Session, make_book
    ):
        book = make_book(metadata_override={"title": "Old"})
        admin_client.put(f"/api/v2/books/{book.id}/metadata", json={"title": ""})
        test_db.refresh(book)
        assert book.metadata_override is None

    def test_unknown_fields_are_ignored(
        self, admin_client: TestClient, test_db: Session, test_book
    ):
        admin_client.put(
            f"/api/v2/books/{test_book.id}/metadata",
            json={"title": "Kept", "file_path": "/etc/passwd", "id": 9999},
        )
        test_db.refresh(test_book)
        assert test_book.metadata_override == {"title": "Kept"}
        assert test_book.file_path is None

    def test_reset_requires_admin(self, authenticated_client: TestClient, test_book):
        response = authenticated_client.delete(
            f"/api/v2/books/{test_book.id}/metadata"
        )
        assert response.status_code == 403

    def test_admin_resets_overrides(
        self, admin_client: TestClient, test_db: Session, make_book
    ):
        book = make_book(metadata_override={"title": "Override"})
        assert (
            admin_client.delete(f"/api/v2/books/{book.id}/metadata").status_code == 200
        )
        test_db.refresh(book)
        assert book.metadata_override is None

    def test_metadata_on_missing_book_is_404(self, admin_client: TestClient):
        assert (
            admin_client.put("/api/v2/books/999999/metadata", json={}).status_code
            == 404
        )


class TestPatchBook:
    def test_toggles_download_enabled(
        self, authenticated_client: TestClient, test_db: Session, make_book
    ):
        book = make_book(download_enabled=True)
        authenticated_client.patch(
            f"/api/v2/books/{book.id}", json={"download_enabled": False}
        )
        test_db.refresh(book)
        assert book.download_enabled is False

    def test_mark_available_clears_the_failure_state(
        self, authenticated_client: TestClient, test_db: Session, make_book
    ):
        book = make_book(
            download_unavailable=True,
            download_error_message="not in your library",
            download_enabled=False,
        )
        authenticated_client.patch(
            f"/api/v2/books/{book.id}", json={"mark_available": True}
        )
        test_db.refresh(book)
        assert book.download_unavailable is False
        assert book.download_error_message is None
        assert book.download_enabled is True

    def test_mark_available_false_is_a_no_op(
        self, authenticated_client: TestClient, test_db: Session, make_book
    ):
        book = make_book(download_unavailable=True)
        authenticated_client.patch(
            f"/api/v2/books/{book.id}", json={"mark_available": False}
        )
        test_db.refresh(book)
        assert book.download_unavailable is True

    def test_patch_missing_book_is_404(self, authenticated_client: TestClient):
        assert (
            authenticated_client.patch("/api/v2/books/999999", json={}).status_code
            == 404
        )


class TestDeleteFile:
    def test_removes_the_file_and_resets_download_state(
        self, authenticated_client: TestClient, test_db: Session, make_book, tmp_path
    ):
        audio = tmp_path / "book.m4b"
        audio.write_bytes(b"audio")
        book = make_book(
            file_path=str(audio),
            file_size=5,
            file_format="m4b",
            downloaded_at=datetime.utcnow(),
            download_unavailable=True,
            download_error_message="stale error",
        )

        assert (
            authenticated_client.delete(f"/api/v2/books/{book.id}/file").status_code
            == 200
        )
        assert not audio.exists()

        test_db.refresh(book)
        assert book.file_path is None
        assert book.file_size is None
        assert book.downloaded_at is None
        # The book becomes downloadable again, and the old failure is cleared.
        assert book.download_enabled is True
        assert book.download_unavailable is False
        assert book.download_error_message is None

    def test_book_row_survives(
        self, authenticated_client: TestClient, test_db: Session, make_book
    ):
        """Deleting the file must not delete the library entry."""
        book = make_book(file_path="audiobooks/gone.m4b")
        authenticated_client.delete(f"/api/v2/books/{book.id}/file")
        assert test_db.query(Book).filter(Book.id == book.id).first() is not None

    def test_absent_file_on_disk_is_not_an_error(
        self, authenticated_client: TestClient, make_book
    ):
        book = make_book(file_path="audiobooks/never-existed.m4b")
        assert (
            authenticated_client.delete(f"/api/v2/books/{book.id}/file").status_code
            == 200
        )


class TestUnmatchBook:
    def test_requires_a_file(self, authenticated_client: TestClient, test_book):
        response = authenticated_client.post(f"/api/v2/books/{test_book.id}/unmatch")
        assert response.status_code == 400

    def test_moves_the_file_to_unassigned(
        self,
        authenticated_client: TestClient,
        test_db: Session,
        make_book,
        tmp_path,
        monkeypatch,
    ):
        from app.config import settings

        monkeypatch.setattr(settings, "audiobooks_path", tmp_path / "audiobooks")
        (tmp_path / "audiobooks").mkdir()
        audio = tmp_path / "audiobooks" / "matched.m4b"
        audio.write_bytes(b"audio")

        book = make_book(
            file_path=str(audio), source=BookSource.AUDIBLE, download_enabled=False
        )
        response = authenticated_client.post(f"/api/v2/books/{book.id}/unmatch")

        assert response.status_code == 200
        assert response.json()["filename"] == "matched.m4b"
        assert (tmp_path / "audiobooks" / "unassigned" / "matched.m4b").exists()
        assert not audio.exists()

        test_db.refresh(book)
        assert book.file_path is None
        # An Audible book becomes re-downloadable; a local one has nothing to
        # download, so the flag is only flipped for Audible sources.
        assert book.download_enabled is True


class TestDeleteBook:
    def test_requires_admin(self, authenticated_client: TestClient, test_book):
        assert (
            authenticated_client.delete(f"/api/v2/books/{test_book.id}").status_code
            == 403
        )

    def test_admin_deletes_row_and_file(
        self, admin_client: TestClient, test_db: Session, make_book, tmp_path
    ):
        audio = tmp_path / "doomed.m4b"
        audio.write_bytes(b"audio")
        book = make_book(title="Doomed", file_path=str(audio))
        book_id = book.id

        response = admin_client.delete(f"/api/v2/books/{book_id}")
        assert response.status_code == 200
        assert "Doomed" in response.json()["message"]
        assert not audio.exists()
        assert test_db.query(Book).filter(Book.id == book_id).first() is None

    def test_missing_book_is_404(self, admin_client: TestClient):
        assert admin_client.delete("/api/v2/books/999999").status_code == 404
