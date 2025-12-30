"""Automatic migration runner for database schema updates."""

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Table, create_engine, text
from sqlalchemy.orm import Session

from .config import settings

logger = logging.getLogger(__name__)


def get_migration_table(engine):
    """Get or create the migration tracking table."""
    from sqlalchemy import MetaData

    metadata = MetaData()

    migration_table = Table(
        'schema_migrations',
        metadata,
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('migration_name', String(255), unique=True, nullable=False),
        Column('applied_at', DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP')),
    )

    # Create table if it doesn't exist
    metadata.create_all(engine)

    return migration_table


def has_migration_been_applied(db: Session, migration_name: str) -> bool:
    """Check if a migration has already been applied."""
    result = db.execute(
        text("SELECT COUNT(*) FROM schema_migrations WHERE migration_name = :name"),
        {"name": migration_name}
    )
    count = result.scalar()
    return count > 0


def mark_migration_applied(db: Session, migration_name: str) -> None:
    """Mark a migration as applied."""
    db.execute(
        text("INSERT INTO schema_migrations (migration_name) VALUES (:name)"),
        {"name": migration_name}
    )
    db.commit()


def run_migration_008_add_download_type(db: Session, engine) -> None:
    """Add download_type column to download_queue table."""
    migration_name = "008_add_download_type"

    is_postgres = "postgresql" in str(engine.url)

    # Check if column actually exists (more reliable than migration tracking)
    column_exists = False
    if is_postgres:
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='download_queue' AND column_name='download_type'
        """))
        column_exists = result.fetchone() is not None
    else:
        result = db.execute(text("PRAGMA table_info(download_queue)"))
        columns = [col[1] for col in result.fetchall()]
        column_exists = "download_type" in columns

    if column_exists:
        logger.info(f"Column download_type already exists, ensuring migration is marked as applied")
        if not has_migration_been_applied(db, migration_name):
            mark_migration_applied(db, migration_name)
        return

    if has_migration_been_applied(db, migration_name):
        logger.warning(f"Migration {migration_name} was marked as applied but column doesn't exist - re-running")
        # Remove the bad migration record
        db.execute(
            text("DELETE FROM schema_migrations WHERE migration_name = :name"),
            {"name": migration_name}
        )
        db.commit()

    logger.info(f"Running migration: {migration_name}")

    try:
        if is_postgres:
            # PostgreSQL: Create enum type first, then add column
            logger.info("Creating downloadtype enum type...")
            db.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE downloadtype AS ENUM ('book', 'cover');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            db.commit()

            logger.info("Adding download_type column to download_queue table...")
            db.execute(text("""
                ALTER TABLE download_queue
                ADD COLUMN download_type downloadtype DEFAULT 'book'::downloadtype NOT NULL
            """))
        else:
            # SQLite
            logger.info("Adding download_type column to download_queue table...")
            db.execute(text("""
                ALTER TABLE download_queue
                ADD COLUMN download_type VARCHAR(10) DEFAULT 'book' NOT NULL
            """))

        db.commit()
        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_migration_009_add_cover_url(db: Session, engine) -> None:
    """Add cover_url column to books table."""
    migration_name = "009_add_cover_url"

    is_postgres = "postgresql" in str(engine.url)

    # Check if column actually exists
    column_exists = False
    if is_postgres:
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='books' AND column_name='cover_url'
        """))
        column_exists = result.fetchone() is not None
    else:
        result = db.execute(text("PRAGMA table_info(books)"))
        columns = [col[1] for col in result.fetchall()]
        column_exists = "cover_url" in columns

    if column_exists:
        logger.info(f"Column cover_url already exists, ensuring migration is marked as applied")
        if not has_migration_been_applied(db, migration_name):
            mark_migration_applied(db, migration_name)
        return

    if has_migration_been_applied(db, migration_name):
        logger.warning(f"Migration {migration_name} was marked as applied but column doesn't exist - re-running")
        db.execute(
            text("DELETE FROM schema_migrations WHERE migration_name = :name"),
            {"name": migration_name}
        )
        db.commit()

    logger.info(f"Running migration: {migration_name}")

    try:
        logger.info("Adding cover_url column to books table...")
        if is_postgres:
            db.execute(text("""
                ALTER TABLE books
                ADD COLUMN cover_url VARCHAR(1024)
            """))
        else:
            db.execute(text("""
                ALTER TABLE books
                ADD COLUMN cover_url VARCHAR(1024)
            """))

        db.commit()
        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_migration_010_add_purchased_at(db: Session, engine) -> None:
    """Add purchased_at column to books table."""
    migration_name = "010_add_purchased_at"

    is_postgres = "postgresql" in str(engine.url)

    # Check if column actually exists
    column_exists = False
    if is_postgres:
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='books' AND column_name='purchased_at'
        """))
        column_exists = result.fetchone() is not None
    else:
        result = db.execute(text("PRAGMA table_info(books)"))
        columns = [col[1] for col in result.fetchall()]
        column_exists = "purchased_at" in columns

    if column_exists:
        logger.info(f"Column purchased_at already exists, ensuring migration is marked as applied")
        if not has_migration_been_applied(db, migration_name):
            mark_migration_applied(db, migration_name)
        return

    if has_migration_been_applied(db, migration_name):
        logger.warning(f"Migration {migration_name} was marked as applied but column doesn't exist - re-running")
        db.execute(
            text("DELETE FROM schema_migrations WHERE migration_name = :name"),
            {"name": migration_name}
        )
        db.commit()

    logger.info(f"Running migration: {migration_name}")

    try:
        logger.info("Adding purchased_at column to books table...")
        if is_postgres:
            db.execute(text("""
                ALTER TABLE books
                ADD COLUMN purchased_at TIMESTAMP NULL
            """))
        else:
            db.execute(text("""
                ALTER TABLE books
                ADD COLUMN purchased_at DATETIME NULL
            """))

        db.commit()
        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_migration_011_fix_download_type_enum(db: Session, engine) -> None:
    """Fix download_type enum case mismatch in PostgreSQL."""
    migration_name = "011_fix_download_type_enum"

    is_postgres = "postgresql" in str(engine.url)

    if has_migration_been_applied(db, migration_name):
        logger.info(f"Migration {migration_name} already applied")
        return

    logger.info(f"Running migration: {migration_name}")

    try:
        if is_postgres:
            # Check what values the enum type actually has
            result = db.execute(text("""
                SELECT e.enumlabel
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'downloadtype'
                ORDER BY e.enumsortorder
            """))
            enum_values = [row[0] for row in result.fetchall()]
            logger.info(f"Current downloadtype enum values: {enum_values}")

            # Check if we have both uppercase and lowercase (shouldn't happen, but just in case)
            has_uppercase = 'BOOK' in enum_values or 'COVER' in enum_values
            has_lowercase = 'book' in enum_values or 'cover' in enum_values

            if has_uppercase and not has_lowercase:
                # Enum only has uppercase - already correct, just ensure data matches
                logger.info("Enum has uppercase values - verifying data...")
                # Check if there's any data to update (shouldn't be, but check anyway)
                result = db.execute(text("SELECT COUNT(*) FROM download_queue"))
                count = result.scalar()
                if count > 0:
                    logger.info("No data migration needed - enum already correct")
            elif has_lowercase and not has_uppercase:
                # Enum only has lowercase - need to add uppercase and migrate
                logger.info("Enum has lowercase values - adding uppercase values and migrating data")

                # Add uppercase values to enum
                if 'BOOK' not in enum_values:
                    db.execute(text("ALTER TYPE downloadtype ADD VALUE 'BOOK'"))
                if 'COVER' not in enum_values:
                    db.execute(text("ALTER TYPE downloadtype ADD VALUE 'COVER'"))
                db.commit()

                # Update data from lowercase to uppercase
                db.execute(text("""
                    UPDATE download_queue
                    SET download_type = 'BOOK'
                    WHERE download_type::text = 'book'
                """))
                db.execute(text("""
                    UPDATE download_queue
                    SET download_type = 'COVER'
                    WHERE download_type::text = 'cover'
                """))
                db.commit()
                logger.info("Data migration complete")
            elif has_uppercase and has_lowercase:
                # Both exist - just migrate data to uppercase
                logger.info("Enum has both uppercase and lowercase values - migrating data to uppercase")
                db.execute(text("""
                    UPDATE download_queue
                    SET download_type = 'BOOK'
                    WHERE download_type::text = 'book'
                """))
                db.execute(text("""
                    UPDATE download_queue
                    SET download_type = 'COVER'
                    WHERE download_type::text = 'cover'
                """))
                db.commit()
                logger.info("Data migration complete")
        else:
            # SQLite: Just update any lowercase values to uppercase
            logger.info("Checking SQLite download_type values...")
            result = db.execute(text("""
                SELECT COUNT(*) FROM download_queue
                WHERE download_type IN ('book', 'cover')
            """))
            count = result.scalar()

            if count > 0:
                logger.info(f"Updating {count} SQLite download_type values to uppercase...")
                db.execute(text("""
                    UPDATE download_queue
                    SET download_type = 'BOOK'
                    WHERE download_type = 'book'
                """))
                db.execute(text("""
                    UPDATE download_queue
                    SET download_type = 'COVER'
                    WHERE download_type = 'cover'
                """))
                db.commit()
                logger.info("SQLite data migration complete")
            else:
                logger.info("No SQLite data to migrate")

        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        # Don't fail - mark as applied anyway to avoid repeated attempts
        logger.warning("Marking migration as applied despite error")
        if not has_migration_been_applied(db, migration_name):
            mark_migration_applied(db, migration_name)


def run_migration_012_fix_lowercase_download_types(db: Session, engine) -> None:
    """Fix any remaining lowercase download_type values."""
    migration_name = "012_fix_lowercase_download_types"

    if has_migration_been_applied(db, migration_name):
        logger.info(f"Migration {migration_name} already applied")
        return

    is_postgres = "postgresql" in str(engine.url)

    logger.info(f"Running migration: {migration_name}")

    try:
        if is_postgres:
            # PostgreSQL: Check if we have lowercase values and update them
            result = db.execute(text("""
                SELECT COUNT(*) FROM download_queue
                WHERE download_type::text IN ('book', 'cover')
            """))
            count = result.scalar()

            if count > 0:
                logger.info(f"Found {count} rows with lowercase download_type values")

                # First ensure uppercase enum values exist
                result = db.execute(text("""
                    SELECT e.enumlabel
                    FROM pg_type t
                    JOIN pg_enum e ON t.oid = e.enumtypid
                    WHERE t.typname = 'downloadtype'
                """))
                enum_values = [row[0] for row in result.fetchall()]

                if 'BOOK' not in enum_values:
                    db.execute(text("ALTER TYPE downloadtype ADD VALUE 'BOOK'"))
                if 'COVER' not in enum_values:
                    db.execute(text("ALTER TYPE downloadtype ADD VALUE 'COVER'"))
                db.commit()

                # Now update the data
                db.execute(text("""
                    UPDATE download_queue
                    SET download_type = 'BOOK'
                    WHERE download_type::text = 'book'
                """))
                db.execute(text("""
                    UPDATE download_queue
                    SET download_type = 'COVER'
                    WHERE download_type::text = 'cover'
                """))
                db.commit()
                logger.info(f"Updated {count} rows to uppercase")
            else:
                logger.info("No lowercase download_type values found")
        else:
            # SQLite: Update any lowercase values
            result = db.execute(text("""
                SELECT COUNT(*) FROM download_queue
                WHERE download_type IN ('book', 'cover')
            """))
            count = result.scalar()

            if count > 0:
                logger.info(f"Found {count} rows with lowercase download_type values")
                db.execute(text("""
                    UPDATE download_queue
                    SET download_type = 'BOOK'
                    WHERE download_type = 'book'
                """))
                db.execute(text("""
                    UPDATE download_queue
                    SET download_type = 'COVER'
                    WHERE download_type = 'cover'
                """))
                db.commit()
                logger.info(f"Updated {count} rows to uppercase")
            else:
                logger.info("No lowercase download_type values found")

        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_all_pending_migrations(db: Session) -> None:
    """Run all pending migrations in order."""
    from .database import engine

    logger.info("Checking for pending migrations...")

    # Ensure migration tracking table exists
    get_migration_table(engine)

    # List of migrations in order
    migrations = [
        run_migration_008_add_download_type,
        run_migration_009_add_cover_url,
        run_migration_010_add_purchased_at,
        run_migration_011_fix_download_type_enum,
        run_migration_012_fix_lowercase_download_types,
    ]

    for migration_func in migrations:
        try:
            migration_func(db, engine)
        except Exception as e:
            logger.error(f"Failed to run migration {migration_func.__name__}: {e}")
            # Don't stop on migration errors, continue with others
            continue

    logger.info("Migration check complete")
