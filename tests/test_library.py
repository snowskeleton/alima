"""Tests for the library API (/api/v2/books)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Book, BookSource, MetadataSource


def _make_book(test_db: Session, **overrides) -> Book:
    fields = dict(
        asin="B001TEST",
        source=BookSource.AUDIBLE,
        title="Test Book Title",
        subtitle="Test Subtitle",
        author="Test Author",
        narrator="Test Narrator",
        series="Test Series",
        series_position="1",
        description="This is a test book description.",
        publisher="Test Publisher",
        duration_seconds=36000,
        metadata_source=MetadataSource.AUDIBLE,
        synced_from_master=False,
    )
    fields.update(overrides)
    book = Book(**fields)
    test_db.add(book)
    test_db.commit()
    test_db.refresh(book)
    return book


@pytest.fixture
def test_book(test_db: Session) -> Book:
    """Create a test book."""
    return _make_book(test_db)


@pytest.mark.integration
class TestBooksAccess:
    """The library is not public."""

    def test_list_requires_auth(self, client: TestClient, test_user):
        response = client.get("/api/v2/books", follow_redirects=False)
        assert response.status_code == 303
        assert "/auth/login" in response.headers["location"]

    def test_detail_requires_auth(self, client: TestClient, test_user, test_book: Book):
        response = client.get(f"/api/v2/books/{test_book.id}", follow_redirects=False)
        assert response.status_code == 303


@pytest.mark.integration
class TestListBooks:
    """Listing, searching and paging."""

    def test_list_returns_books_with_a_total(
        self, authenticated_client: TestClient, test_book: Book
    ):
        data = authenticated_client.get("/api/v2/books").json()

        assert data["total"] == len(data["books"]) == 1
        assert data["books"][0]["title"] == test_book.title

    def test_search_matches_across_fields(
        self, authenticated_client: TestClient, test_db: Session
    ):
        """Search covers title, author, series and narrator, and is case-insensitive."""
        _make_book(test_db, asin="B1", title="Dune", author="Frank Herbert",
                   series="Dune Chronicles", narrator="Scott Brick")
        _make_book(test_db, asin="B2", title="Neuromancer", author="William Gibson",
                   series=None, narrator="Robertson Dean")

        def titles(query):
            data = authenticated_client.get(f"/api/v2/books?search={query}").json()
            return {b["title"] for b in data["books"]}

        assert titles("dune") == {"Dune"}
        assert titles("gibson") == {"Neuromancer"}
        assert titles("Scott Brick") == {"Dune"}
        assert titles("chronicles") == {"Dune"}
        assert titles("nothing-matches-this") == set()

    def test_pagination_walks_the_whole_library_without_repeats(
        self, authenticated_client: TestClient, test_db: Session
    ):
        for i in range(5):
            _make_book(test_db, asin=f"PAGE{i}", title=f"Book {i}")

        seen = []
        for offset in range(0, 5, 2):
            page = authenticated_client.get(
                f"/api/v2/books?limit=2&offset={offset}&sort=asin&order=asc"
            ).json()
            assert page["total"] == 5
            assert len(page["books"]) <= 2
            seen.extend(b["id"] for b in page["books"])

        assert len(seen) == 5
        assert len(set(seen)) == 5

    def test_total_counts_matches_not_just_the_page(
        self, authenticated_client: TestClient, test_db: Session
    ):
        for i in range(3):
            _make_book(test_db, asin=f"T{i}", title=f"Match {i}")

        data = authenticated_client.get("/api/v2/books?limit=1&search=Match").json()

        assert len(data["books"]) == 1
        assert data["total"] == 3

    def test_status_filter_separates_downloaded_from_pending(
        self, authenticated_client: TestClient, test_db: Session
    ):
        _make_book(test_db, asin="HAVE", title="Downloaded",
                   file_path="audiobooks/downloaded.m4b")
        _make_book(test_db, asin="WANT", title="Pending", download_enabled=True)

        downloaded = authenticated_client.get("/api/v2/books?status=downloaded").json()
        pending = authenticated_client.get("/api/v2/books?status=pending").json()

        assert [b["title"] for b in downloaded["books"]] == ["Downloaded"]
        assert [b["title"] for b in pending["books"]] == ["Pending"]

    def test_sorting_is_reversible(
        self, authenticated_client: TestClient, test_db: Session
    ):
        for title in ("Charlie", "Alpha", "Bravo"):
            _make_book(test_db, asin=title, title=title)

        ascending = authenticated_client.get(
            "/api/v2/books?sort=title&order=asc"
        ).json()["books"]
        descending = authenticated_client.get(
            "/api/v2/books?sort=title&order=desc"
        ).json()["books"]

        titles = [b["title"] for b in ascending]
        assert titles == sorted(titles)
        assert [b["title"] for b in descending] == list(reversed(titles))


@pytest.mark.integration
class TestBookDetail:
    """Single-book detail."""

    def test_detail_describes_the_book(
        self, authenticated_client: TestClient, test_book: Book
    ):
        data = authenticated_client.get(f"/api/v2/books/{test_book.id}").json()

        assert data["id"] == test_book.id
        assert data["title"] == test_book.title
        assert data["author"] == test_book.author
        assert data["asin"] == test_book.asin

    def test_detail_reports_download_state(
        self, authenticated_client: TestClient, test_book: Book, test_db: Session
    ):
        """A queued download is surfaced on the book so the UI can show progress."""
        from app.models import AudibleAccount, DownloadQueue, DownloadStatus

        account = AudibleAccount(
            username="queue@example.com",
            auth_file_path="/tmp/auth.json",
            activation_bytes="deadbeef",
            marketplace="us",
        )
        test_db.add(account)
        test_db.commit()

        test_db.add(
            DownloadQueue(
                book_id=test_book.id,
                audible_account_id=account.id,
                asin=test_book.asin,
                status=DownloadStatus.PENDING,
            )
        )
        test_db.commit()

        data = authenticated_client.get(f"/api/v2/books/{test_book.id}").json()

        assert data["download_queue"]["status"] == "pending"

    def test_detail_of_unknown_book(self, authenticated_client: TestClient):
        response = authenticated_client.get("/api/v2/books/99999")
        assert response.status_code == 404
