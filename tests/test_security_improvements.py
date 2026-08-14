"""Tests for security and performance hardening."""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Book, BookSource, Feed, FeedBook, FeedType, MetadataSource


@pytest.mark.unit
class TestSecretKeyValidation:
    """SECRET_KEY validation at startup."""

    def test_empty_secret_key_raises_error(self):
        with pytest.raises(ValueError, match="SECRET_KEY must be at least 32 characters"):
            Settings(secret_key="")

    def test_short_secret_key_raises_error(self):
        with pytest.raises(ValueError, match="SECRET_KEY must be at least 32 characters"):
            Settings(secret_key="tooshort")

    def test_valid_secret_key_accepted(self):
        valid_key = "a" * 32
        settings = Settings(secret_key=valid_key)
        assert settings.secret_key == valid_key


@pytest.mark.integration
class TestRateLimiting:
    """Rate limiting on the login endpoint."""

    def test_login_is_rate_limited(self, client, test_user):
        """Repeated login attempts from one address are eventually refused."""
        from app.routers.api_v2.auth import limiter

        limiter.reset()
        try:
            statuses = [
                client.post(
                    "/api/v2/auth/login", json={"email": test_user.email}
                ).status_code
                for _ in range(15)
            ]
        finally:
            limiter.reset()

        assert 200 in statuses, "the first attempts should be allowed through"
        assert 429 in statuses, "sustained attempts should be throttled"


@pytest.mark.unit
class TestDatabaseIndexes:
    """Columns that carry the hot queries are indexed."""

    @pytest.mark.parametrize(
        "table,column",
        [
            ("books", "asin"),
            ("books", "source"),
            ("books", "file_path"),
            ("books", "audible_account_id"),
            ("download_queue", "status"),
            ("feeds", "slug"),
            ("magic_links", "token"),
        ],
    )
    def test_column_is_indexed(self, test_engine, table, column):
        inspector = inspect(test_engine)
        indexed = {
            col
            for index in inspector.get_indexes(table)
            for col in index["column_names"]
        }
        # Unique constraints and primary keys index implicitly.
        for constraint in [inspector.get_pk_constraint(table)]:
            indexed.update(constraint.get("constrained_columns") or [])
        for unique in inspector.get_unique_constraints(table):
            indexed.update(unique.get("column_names") or [])

        assert column in indexed, f"{table}.{column} should be indexed"


@pytest.mark.unit
class TestForeignKeyCascades:
    """Deleting a parent row does not leave orphans behind."""

    def test_feed_delete_declares_cascade(self, test_engine):
        """The feed_books -> feeds FK is declared ON DELETE CASCADE."""
        fks = inspect(test_engine).get_foreign_keys("feed_books")
        feed_fk = next(fk for fk in fks if fk["referred_table"] == "feeds")

        assert feed_fk["options"].get("ondelete") == "CASCADE"

    def test_delete_feed_removes_its_feed_books(self, test_db: Session):
        feed = Feed(
            name="Cascade Feed",
            slug="cascade-feed",
            feed_type=FeedType.MANUAL,
            is_public=True,
        )
        book = Book(
            asin="BCASCADE",
            source=BookSource.AUDIBLE,
            title="Cascade Book",
            author="Author",
            metadata_source=MetadataSource.AUDIBLE,
        )
        test_db.add_all([feed, book])
        test_db.commit()

        test_db.add(FeedBook(feed_id=feed.id, book_id=book.id))
        test_db.commit()

        test_db.delete(feed)
        test_db.commit()

        assert test_db.query(FeedBook).filter(FeedBook.feed_id == feed.id).count() == 0
        # The book itself is shared content and must survive.
        assert test_db.query(Book).filter(Book.id == book.id).first() is not None

    def test_delete_user_keeps_their_magic_links(self, test_db: Session):
        """Magic links key off email, not a user FK, so they are not cascaded away."""
        from datetime import datetime, timedelta

        from app.models import MagicLink, User, UserRole

        user = User(email="cascade_test@example.com", role=UserRole.ADMIN)
        test_db.add(user)
        test_db.commit()

        link = MagicLink(
            email=user.email,
            token="test_token_cascade",
            expires_at=datetime.utcnow() + timedelta(minutes=15),
        )
        test_db.add(link)
        test_db.commit()
        link_id = link.id

        test_db.delete(user)
        test_db.commit()

        assert test_db.query(MagicLink).filter(MagicLink.id == link_id).first() is not None


@pytest.mark.unit
class TestSettingsCache:
    """Centralized settings cache."""

    def test_missing_key_falls_back_to_default(self):
        from app.utils.settings_cache import get_cached_setting

        assert get_cached_setting("nonexistent_key", "default_value") == "default_value"

    def test_value_is_coerced_to_the_requested_type(self):
        from app.utils.settings_cache import get_cached_setting

        result = get_cached_setting("nonexistent_int", 42, int)
        assert result == 42
        assert isinstance(result, int)

    def test_cleared_cache_still_serves_values(self):
        from app.utils.settings_cache import clear_settings_cache, get_cached_setting

        get_cached_setting("test_key", "value")
        clear_settings_cache()

        assert get_cached_setting("test_key", "value") == "value"


@pytest.mark.unit
class TestSessionExpiration:
    """Session lifetime comes from settings with a usable fallback."""

    def test_expiration_falls_back_to_a_week(self):
        from app.routers.api_v2.auth import _get_session_expiration_hours

        assert _get_session_expiration_hours() == 168


@pytest.mark.unit
class TestPathTraversalProtection:
    """File serving refuses to escape its base directory."""

    def test_cover_path_cannot_escape_covers_dir(self):
        from app.routers.files import serve_cover

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(serve_cover("../../../../etc/passwd"))

        assert exc_info.value.status_code in (400, 403)

    def test_legitimate_cover_subdirectory_is_allowed(self, tmp_path, monkeypatch):
        """Nested cover paths (e.g. feeds/<uuid>.jpg) still resolve."""
        from app.config import settings
        from app.routers.files import serve_cover

        monkeypatch.setattr(settings, "covers_path", tmp_path)
        nested = tmp_path / "feeds"
        nested.mkdir()
        (nested / "cover.jpg").write_bytes(b"not-really-a-jpeg")

        response = asyncio.run(serve_cover("feeds/cover.jpg"))

        assert response.media_type == "image/jpeg"

    def test_audiobook_with_a_traversing_path_is_not_served(
        self, client, test_db: Session
    ):
        book = Book(
            asin="BTRAVERSE",
            source=BookSource.AUDIBLE,
            title="Traversal Book",
            author="Author",
            metadata_source=MetadataSource.AUDIBLE,
            file_path="../../../../etc/passwd",
        )
        test_db.add(book)
        test_db.commit()

        response = client.get(f"/files/audiobooks/{book.id}.m4b")

        assert response.status_code in (400, 403, 404)
        assert b"root:" not in response.content


@pytest.mark.integration
class TestRSSFeedQueryCount:
    """Feed rendering must not issue a query per book."""

    def _make_feed_with_books(self, test_db: Session, slug: str, count: int) -> Feed:
        feed = Feed(
            name=f"Feed {slug}",
            slug=slug,
            feed_type=FeedType.MANUAL,
            is_public=True,
        )
        test_db.add(feed)
        test_db.commit()

        for i in range(count):
            book = Book(
                asin=f"{slug}-{i}",
                source=BookSource.AUDIBLE,
                title=f"Book {i}",
                author="Author",
                metadata_source=MetadataSource.AUDIBLE,
                file_path=f"audiobooks/{slug}-{i}.m4b",
                file_size=1024,
                file_format="m4b",
            )
            test_db.add(book)
            test_db.commit()
            test_db.add(FeedBook(feed_id=feed.id, book_id=book.id, position=i))
        test_db.commit()
        return feed

    def test_query_count_does_not_grow_with_the_feed(
        self, client, test_db: Session, test_engine
    ):
        from sqlalchemy import event

        small = self._make_feed_with_books(test_db, "n1-small", 2)
        large = self._make_feed_with_books(test_db, "n1-large", 12)

        counts = {}

        for slug in (small.slug, large.slug):
            statements = []

            def record(conn, cursor, statement, params, context, executemany):
                statements.append(statement)

            event.listen(test_engine, "before_cursor_execute", record)
            try:
                response = client.get(f"/feeds/{slug}.xml")
            finally:
                event.remove(test_engine, "before_cursor_execute", record)

            assert response.status_code == 200
            counts[slug] = len(statements)

        # Six times the books should not mean six times the queries.
        assert counts[large.slug] <= counts[small.slug] + 2, counts
