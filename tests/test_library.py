"""Tests for library routes and functionality."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AudibleAccount, Book, BookSource, MetadataSource, User


@pytest.fixture
def test_book(test_db: Session) -> Book:
    """Create a test book."""
    book = Book(
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
    test_db.add(book)
    test_db.commit()
    test_db.refresh(book)
    return book


@pytest.mark.integration
class TestLibraryRoutes:
    """Test library routes."""

    def test_library_index_requires_auth(self, client: TestClient):
        """Test library index requires authentication."""
        response = client.get("/library")
        assert response.status_code == 401

    def test_library_index_authenticated(
        self, authenticated_client: TestClient, test_book: Book
    ):
        """Test library index with authenticated user."""
        response = authenticated_client.get("/library")
        assert response.status_code == 200
        assert b"Audiobook Library" in response.content

    def test_library_search(
        self, authenticated_client: TestClient, test_book: Book
    ):
        """Test library search functionality."""
        response = authenticated_client.get("/library?search=Test")
        assert response.status_code == 200

    def test_book_detail_requires_auth(self, client: TestClient, test_book: Book):
        """Test book detail requires authentication."""
        response = client.get(f"/library/{test_book.id}")
        assert response.status_code == 401

    def test_book_detail_authenticated(
        self, authenticated_client: TestClient, test_book: Book
    ):
        """Test book detail with authenticated user."""
        response = authenticated_client.get(f"/library/{test_book.id}")
        assert response.status_code == 200
        assert b"Test Book Title" in response.content

    def test_book_detail_not_found(self, authenticated_client: TestClient):
        """Test book detail with non-existent book."""
        response = authenticated_client.get("/library/99999")
        assert response.status_code == 404


@pytest.mark.integration
class TestLibraryAPI:
    """Test library API endpoints."""

    def test_list_books_api(
        self, authenticated_client: TestClient, test_book: Book
    ):
        """Test GET /library/api/books."""
        response = authenticated_client.get("/library/api/books")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["title"] == "Test Book Title"

    def test_list_books_api_search(
        self, authenticated_client: TestClient, test_book: Book
    ):
        """Test API book search."""
        response = authenticated_client.get("/library/api/books?search=Test")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_list_books_api_pagination(
        self, authenticated_client: TestClient, test_book: Book
    ):
        """Test API pagination."""
        response = authenticated_client.get("/library/api/books?limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1

    def test_get_book_api(
        self, authenticated_client: TestClient, test_book: Book
    ):
        """Test GET /library/api/books/{book_id}."""
        response = authenticated_client.get(f"/library/api/books/{test_book.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_book.id
        assert data["title"] == "Test Book Title"
        assert data["author"] == "Test Author"

    def test_get_book_api_not_found(self, authenticated_client: TestClient):
        """Test API get book not found."""
        response = authenticated_client.get("/library/api/books/99999")
        assert response.status_code == 404
