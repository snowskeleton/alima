"""Tests for the numbered migrations in app.migrations_runner.

The runner swallows migration failures so one bad migration can't stop the app
from booting, which also means a broken migration is silent in production. These
tests run them against a real database instead.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.migrations_runner import (
    get_migration_table,
    has_migration_been_applied,
    run_migration_021_add_feed_sort_order,
)
from app.models import FeedType


def _feeds_columns(db: Session, engine) -> set[str]:
    if "postgresql" in str(engine.url):
        result = db.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='feeds'"
        ))
        return {row[0] for row in result.fetchall()}
    result = db.execute(text("PRAGMA table_info(feeds)"))
    return {col[1] for col in result.fetchall()}


class TestMigration021FeedSortOrder:
    @pytest.fixture
    def pre_migration(self, test_db: Session, test_engine, make_feed, test_user):
        """A feeds table as it looked before sort_order existed, with a row in it.

        The schema here is built from the models, so the column already exists;
        dropping it is what puts the database back in the state the migration is
        actually written for.
        """
        make_feed(test_user, feed_type=FeedType.MANUAL, slug="pre-existing")
        get_migration_table(test_engine)
        test_db.execute(text("ALTER TABLE feeds DROP COLUMN sort_order"))
        test_db.execute(text(
            "DELETE FROM schema_migrations WHERE migration_name = '021_add_feed_sort_order'"
        ))
        test_db.commit()
        assert "sort_order" not in _feeds_columns(test_db, test_engine)
        return test_db

    def test_adds_the_column_and_records_itself(self, pre_migration: Session, test_engine):
        run_migration_021_add_feed_sort_order(pre_migration, test_engine)

        assert "sort_order" in _feeds_columns(pre_migration, test_engine)
        assert has_migration_been_applied(pre_migration, "021_add_feed_sort_order")

    def test_leaves_existing_feeds_on_their_default_order(
        self, pre_migration: Session, test_engine
    ):
        """NULL means "the default for this feed type", so nothing re-sorts."""
        run_migration_021_add_feed_sort_order(pre_migration, test_engine)

        value = pre_migration.execute(
            text("SELECT sort_order FROM feeds WHERE slug = 'pre-existing'")
        ).scalar()
        assert value is None

    def test_is_idempotent(self, pre_migration: Session, test_engine):
        run_migration_021_add_feed_sort_order(pre_migration, test_engine)
        # A second pass must not try to add the column again and blow up.
        run_migration_021_add_feed_sort_order(pre_migration, test_engine)

        assert "sort_order" in _feeds_columns(pre_migration, test_engine)

    def test_marks_itself_applied_when_the_column_already_exists(
        self, test_db: Session, test_engine
    ):
        """A database created from the models has the column but no history row."""
        get_migration_table(test_engine)
        test_db.execute(text(
            "DELETE FROM schema_migrations WHERE migration_name = '021_add_feed_sort_order'"
        ))
        test_db.commit()

        run_migration_021_add_feed_sort_order(test_db, test_engine)

        assert has_migration_been_applied(test_db, "021_add_feed_sort_order")

    def test_re_runs_when_marked_applied_but_the_column_is_missing(
        self, pre_migration: Session, test_engine
    ):
        """A history row that lies about the schema must not skip the ALTER."""
        from app.migrations_runner import mark_migration_applied

        mark_migration_applied(pre_migration, "021_add_feed_sort_order")

        run_migration_021_add_feed_sort_order(pre_migration, test_engine)

        assert "sort_order" in _feeds_columns(pre_migration, test_engine)
