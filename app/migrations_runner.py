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
        logger.debug(f"Column download_type already exists, ensuring migration is marked as applied")
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

    logger.debug(f"Running migration: {migration_name}")

    try:
        if is_postgres:
            # PostgreSQL: Create enum type first, then add column
            logger.debug("Creating downloadtype enum type...")
            db.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE downloadtype AS ENUM ('book', 'cover');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            db.commit()

            logger.debug("Adding download_type column to download_queue table...")
            db.execute(text("""
                ALTER TABLE download_queue
                ADD COLUMN download_type downloadtype DEFAULT 'book'::downloadtype NOT NULL
            """))
        else:
            # SQLite
            logger.debug("Adding download_type column to download_queue table...")
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
        logger.debug(f"Column cover_url already exists, ensuring migration is marked as applied")
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

    logger.debug(f"Running migration: {migration_name}")

    try:
        logger.debug("Adding cover_url column to books table...")
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
        logger.debug(f"Column purchased_at already exists, ensuring migration is marked as applied")
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

    logger.debug(f"Running migration: {migration_name}")

    try:
        logger.debug("Adding purchased_at column to books table...")
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
        logger.debug(f"Migration {migration_name} already applied")
        return

    logger.debug(f"Running migration: {migration_name}")

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
            logger.debug(f"Current downloadtype enum values: {enum_values}")

            # Check if we have both uppercase and lowercase (shouldn't happen, but just in case)
            has_uppercase = 'BOOK' in enum_values or 'COVER' in enum_values
            has_lowercase = 'book' in enum_values or 'cover' in enum_values

            if has_uppercase and not has_lowercase:
                # Enum only has uppercase - already correct, just ensure data matches
                logger.debug("Enum has uppercase values - verifying data...")
                # Check if there's any data to update (shouldn't be, but check anyway)
                result = db.execute(text("SELECT COUNT(*) FROM download_queue"))
                count = result.scalar()
                if count > 0:
                    logger.debug("No data migration needed - enum already correct")
            elif has_lowercase and not has_uppercase:
                # Enum only has lowercase - need to add uppercase and migrate
                logger.debug("Enum has lowercase values - adding uppercase values and migrating data")

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
                logger.debug("Data migration complete")
            elif has_uppercase and has_lowercase:
                # Both exist - just migrate data to uppercase
                logger.debug("Enum has both uppercase and lowercase values - migrating data to uppercase")
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
                logger.debug("Data migration complete")
        else:
            # SQLite: Just update any lowercase values to uppercase
            logger.debug("Checking SQLite download_type values...")
            result = db.execute(text("""
                SELECT COUNT(*) FROM download_queue
                WHERE download_type IN ('book', 'cover')
            """))
            count = result.scalar()

            if count > 0:
                logger.debug(f"Updating {count} SQLite download_type values to uppercase...")
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
                logger.debug("SQLite data migration complete")
            else:
                logger.debug("No SQLite data to migrate")

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
        logger.debug(f"Migration {migration_name} already applied")
        return

    is_postgres = "postgresql" in str(engine.url)

    logger.debug(f"Running migration: {migration_name}")

    try:
        if is_postgres:
            # PostgreSQL: Check if we have lowercase values and update them
            result = db.execute(text("""
                SELECT COUNT(*) FROM download_queue
                WHERE download_type::text IN ('book', 'cover')
            """))
            count = result.scalar()

            if count > 0:
                logger.debug(f"Found {count} rows with lowercase download_type values")

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
                logger.debug(f"Updated {count} rows to uppercase")
            else:
                logger.debug("No lowercase download_type values found")
        else:
            # SQLite: Update any lowercase values
            result = db.execute(text("""
                SELECT COUNT(*) FROM download_queue
                WHERE download_type IN ('book', 'cover')
            """))
            count = result.scalar()

            if count > 0:
                logger.debug(f"Found {count} rows with lowercase download_type values")
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
                logger.debug(f"Updated {count} rows to uppercase")
            else:
                logger.debug("No lowercase download_type values found")

        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_migration_013_add_indexes_and_cascades(db: Session, engine) -> None:
    """
    Migration 013: Add database indexes and foreign key cascades.

    Changes:
    - Add indexes on: file_path, audible_account_id, status, source, synced_from_master
    - Add CASCADE/SET NULL to foreign key constraints
    """
    migration_name = "013_add_indexes_and_cascades"

    if has_migration_been_applied(db, migration_name):
        logger.debug(f"Migration {migration_name} already applied, skipping")
        return

    logger.debug(f"Running migration {migration_name}...")

    try:
        is_postgresql = engine.url.drivername.startswith("postgresql")

        if is_postgresql:
            # PostgreSQL: Add indexes
            logger.debug("Adding database indexes...")

            # Check and add indexes if they don't exist
            indexes_to_add = [
                ("CREATE INDEX IF NOT EXISTS idx_books_file_path ON books(file_path)", "books.file_path"),
                ("CREATE INDEX IF NOT EXISTS idx_books_audible_account_id ON books(audible_account_id)", "books.audible_account_id"),
                ("CREATE INDEX IF NOT EXISTS idx_books_source ON books(source)", "books.source"),
                ("CREATE INDEX IF NOT EXISTS idx_books_synced_from_master ON books(synced_from_master)", "books.synced_from_master"),
                ("CREATE INDEX IF NOT EXISTS idx_download_queue_status ON download_queue(status)", "download_queue.status"),
            ]

            for sql, index_name in indexes_to_add:
                try:
                    db.execute(text(sql))
                    logger.debug(f"  ✓ Added index on {index_name}")
                except Exception as e:
                    logger.warning(f"  ⚠ Failed to add index on {index_name}: {e}")

            db.commit()

            # PostgreSQL: Update foreign key constraints
            # Note: This is complex - we need to drop and recreate constraints
            logger.debug("Updating foreign key constraints with CASCADE behavior...")

            fk_updates = [
                # Invites: created_by -> users.id (CASCADE)
                {
                    "table": "invites",
                    "constraint": "invites_created_by_fkey",
                    "column": "created_by",
                    "ref_table": "users",
                    "ref_column": "id",
                    "action": "CASCADE"
                },
                # Books: audible_account_id -> audible_accounts.id (SET NULL)
                {
                    "table": "books",
                    "constraint": "books_audible_account_id_fkey",
                    "column": "audible_account_id",
                    "ref_table": "audible_accounts",
                    "ref_column": "id",
                    "action": "SET NULL"
                },
                # Feeds: user_id -> users.id (SET NULL)
                {
                    "table": "feeds",
                    "constraint": "feeds_user_id_fkey",
                    "column": "user_id",
                    "ref_table": "users",
                    "ref_column": "id",
                    "action": "SET NULL"
                },
                # FeedBooks: feed_id -> feeds.id (CASCADE)
                {
                    "table": "feed_books",
                    "constraint": "feed_books_feed_id_fkey",
                    "column": "feed_id",
                    "ref_table": "feeds",
                    "ref_column": "id",
                    "action": "CASCADE"
                },
                # FeedBooks: book_id -> books.id (CASCADE)
                {
                    "table": "feed_books",
                    "constraint": "feed_books_book_id_fkey",
                    "column": "book_id",
                    "ref_table": "books",
                    "ref_column": "id",
                    "action": "CASCADE"
                },
                # DownloadQueue: book_id -> books.id (CASCADE)
                {
                    "table": "download_queue",
                    "constraint": "download_queue_book_id_fkey",
                    "column": "book_id",
                    "ref_table": "books",
                    "ref_column": "id",
                    "action": "CASCADE"
                },
                # DownloadQueue: audible_account_id -> audible_accounts.id (CASCADE)
                {
                    "table": "download_queue",
                    "constraint": "download_queue_audible_account_id_fkey",
                    "column": "audible_account_id",
                    "ref_table": "audible_accounts",
                    "ref_column": "id",
                    "action": "CASCADE"
                },
            ]

            for fk in fk_updates:
                try:
                    # Drop old constraint
                    db.execute(text(f"""
                        ALTER TABLE {fk['table']}
                        DROP CONSTRAINT IF EXISTS {fk['constraint']}
                    """))

                    # Add new constraint with CASCADE/SET NULL
                    db.execute(text(f"""
                        ALTER TABLE {fk['table']}
                        ADD CONSTRAINT {fk['constraint']}
                        FOREIGN KEY ({fk['column']})
                        REFERENCES {fk['ref_table']}({fk['ref_column']})
                        ON DELETE {fk['action']}
                    """))

                    logger.debug(f"  ✓ Updated {fk['table']}.{fk['column']} -> {fk['action']}")
                except Exception as e:
                    logger.warning(f"  ⚠ Failed to update FK {fk['table']}.{fk['column']}: {e}")

            db.commit()

        else:
            # SQLite: Add indexes
            logger.debug("Adding database indexes (SQLite)...")

            indexes_to_add = [
                ("CREATE INDEX IF NOT EXISTS idx_books_file_path ON books(file_path)", "books.file_path"),
                ("CREATE INDEX IF NOT EXISTS idx_books_audible_account_id ON books(audible_account_id)", "books.audible_account_id"),
                ("CREATE INDEX IF NOT EXISTS idx_books_source ON books(source)", "books.source"),
                ("CREATE INDEX IF NOT EXISTS idx_books_synced_from_master ON books(synced_from_master)", "books.synced_from_master"),
                ("CREATE INDEX IF NOT EXISTS idx_download_queue_status ON download_queue(status)", "download_queue.status"),
            ]

            for sql, index_name in indexes_to_add:
                try:
                    db.execute(text(sql))
                    logger.debug(f"  ✓ Added index on {index_name}")
                except Exception as e:
                    logger.warning(f"  ⚠ Failed to add index on {index_name}: {e}")

            db.commit()

            # SQLite: Cannot modify foreign key constraints on existing tables
            # They must be recreated, which is complex and risky
            # Log a warning but continue
            logger.warning("SQLite detected: Foreign key CASCADE updates require table recreation")
            logger.warning("Skipping FK updates for SQLite (will be applied on next table recreation)")

        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_migration_014_add_user_notifications(db: Session, engine) -> None:
    """Add receive_notifications column to users table."""
    migration_name = "014_add_user_notifications"

    is_postgres = "postgresql" in str(engine.url)

    # Check if column actually exists
    column_exists = False
    if is_postgres:
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users' AND column_name='receive_notifications'
        """))
        column_exists = result.fetchone() is not None
    else:
        result = db.execute(text("PRAGMA table_info(users)"))
        columns = [col[1] for col in result.fetchall()]
        column_exists = "receive_notifications" in columns

    if column_exists:
        logger.debug(f"Column receive_notifications already exists, ensuring migration is marked as applied")
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

    logger.debug(f"Running migration: {migration_name}")

    try:
        logger.debug("Adding receive_notifications column to users table...")
        if is_postgres:
            db.execute(text("""
                ALTER TABLE users
                ADD COLUMN receive_notifications BOOLEAN DEFAULT FALSE NOT NULL
            """))
            # Enable notifications for existing admin users
            logger.debug("Enabling notifications for existing admin users...")
            db.execute(text("""
                UPDATE users
                SET receive_notifications = TRUE
                WHERE role = 'ADMIN'
            """))
        else:
            db.execute(text("""
                ALTER TABLE users
                ADD COLUMN receive_notifications BOOLEAN DEFAULT 0 NOT NULL
            """))
            # Enable notifications for existing admin users
            logger.debug("Enabling notifications for existing admin users...")
            db.execute(text("""
                UPDATE users
                SET receive_notifications = 1
                WHERE role = 'ADMIN'
            """))

        db.commit()
        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_migration_015_magic_links(db: Session, engine) -> None:
    """Make password_hash nullable and create magic_links table."""
    migration_name = "015_magic_links"

    if has_migration_been_applied(db, migration_name):
        logger.debug(f"Migration {migration_name} already applied")
        return

    is_postgres = "postgresql" in str(engine.url)

    logger.debug(f"Running migration: {migration_name}")

    try:
        # Step 1: Make password_hash nullable
        if is_postgres:
            db.execute(text("""
                ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL
            """))
        else:
            # SQLite doesn't support ALTER COLUMN, but columns are nullable by default
            # unless explicitly marked NOT NULL. We need to recreate the table or
            # just skip since SQLite doesn't enforce NOT NULL on ALTER ADD.
            # For SQLite, we'll create a new table and copy data.
            result = db.execute(text("PRAGMA table_info(users)"))
            columns = result.fetchall()
            password_col = [c for c in columns if c[1] == 'password_hash']
            if password_col and password_col[0][3] == 1:  # notnull flag
                logger.debug("Recreating users table with nullable password_hash (SQLite)...")
                # Get current column definitions
                col_defs = []
                for col in columns:
                    col_name = col[1]
                    col_type = col[2]
                    notnull = col[3]
                    default = col[4]
                    pk = col[5]

                    parts = [col_name, col_type]
                    if pk:
                        parts.append("PRIMARY KEY AUTOINCREMENT")
                    elif col_name == 'password_hash':
                        # Make it nullable (skip NOT NULL)
                        pass
                    elif notnull:
                        parts.append("NOT NULL")

                    if default is not None:
                        parts.append(f"DEFAULT {default}")

                    col_defs.append(" ".join(parts))

                col_names = [col[1] for col in columns]
                col_list = ", ".join(col_names)
                col_def_str = ", ".join(col_defs)

                db.execute(text(f"CREATE TABLE users_new ({col_def_str})"))
                db.execute(text(f"INSERT INTO users_new ({col_list}) SELECT {col_list} FROM users"))
                db.execute(text("DROP TABLE users"))
                db.execute(text("ALTER TABLE users_new RENAME TO users"))
                # Recreate indexes
                db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email)"))

        db.commit()
        logger.debug("password_hash column is now nullable")

        # Step 2: Create magic_links table
        if is_postgres:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS magic_links (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    token VARCHAR(255) NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_magic_links_email ON magic_links(email)"))
            db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_magic_links_token ON magic_links(token)"))
        else:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS magic_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR(255) NOT NULL,
                    token VARCHAR(255) NOT NULL UNIQUE,
                    expires_at DATETIME NOT NULL,
                    used BOOLEAN DEFAULT 0 NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_magic_links_email ON magic_links(email)"))
            db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_magic_links_token ON magic_links(token)"))

        db.commit()
        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_migration_016_create_api_keys(db: Session, engine) -> None:
    """Create api_keys table."""
    migration_name = "016_create_api_keys"

    if has_migration_been_applied(db, migration_name):
        logger.debug(f"Migration {migration_name} already applied")
        return

    is_postgres = "postgresql" in str(engine.url)

    # Check if table already exists
    table_exists = False
    if is_postgres:
        result = db.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name='api_keys'
        """))
        table_exists = result.fetchone() is not None
    else:
        result = db.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='api_keys'
        """))
        table_exists = result.fetchone() is not None

    if table_exists:
        logger.debug("Table api_keys already exists, marking migration as applied")
        mark_migration_applied(db, migration_name)
        return

    logger.debug(f"Running migration: {migration_name}")

    try:
        if is_postgres:
            db.execute(text("""
                CREATE TABLE api_keys (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    key_prefix VARCHAR(8) NOT NULL,
                    key_hash VARCHAR(64) NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            db.execute(text("CREATE INDEX ix_api_keys_key_hash ON api_keys(key_hash)"))
        else:
            db.execute(text("""
                CREATE TABLE api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    key_prefix VARCHAR(8) NOT NULL,
                    key_hash VARCHAR(64) NOT NULL UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            db.execute(text("CREATE INDEX ix_api_keys_key_hash ON api_keys(key_hash)"))

        db.commit()
        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_migration_017_add_b2_keys(db: Session, engine) -> None:
    """Add Backblaze B2 storage key columns to the books table."""
    migration_name = "017_add_b2_keys"

    is_postgres = "postgresql" in str(engine.url)

    column_exists = False
    if is_postgres:
        result = db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='books' AND column_name='b2_audio_key'
        """))
        column_exists = result.fetchone() is not None
    else:
        result = db.execute(text("PRAGMA table_info(books)"))
        columns = [col[1] for col in result.fetchall()]
        column_exists = "b2_audio_key" in columns

    if column_exists:
        logger.debug("B2 key columns already exist, ensuring migration is marked as applied")
        if not has_migration_been_applied(db, migration_name):
            mark_migration_applied(db, migration_name)
        return

    if has_migration_been_applied(db, migration_name):
        logger.warning(f"Migration {migration_name} was marked as applied but columns don't exist - re-running")
        db.execute(text("DELETE FROM schema_migrations WHERE migration_name = :name"), {"name": migration_name})
        db.commit()

    logger.debug(f"Running migration: {migration_name}")

    try:
        db.execute(text("ALTER TABLE books ADD COLUMN b2_audio_key VARCHAR(512)"))
        db.execute(text("ALTER TABLE books ADD COLUMN b2_cover_key VARCHAR(512)"))
        db.commit()
        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_migration_018_strip_html_descriptions(db: Session, engine) -> None:
    """Flatten HTML in book descriptions synced from Audible to plain text."""
    migration_name = "018_strip_html_descriptions"

    if has_migration_been_applied(db, migration_name):
        return

    logger.debug(f"Running migration: {migration_name}")

    from .utils.html_text import html_to_text

    try:
        rows = db.execute(text(
            "SELECT id, description FROM books "
            "WHERE description IS NOT NULL AND description LIKE '%<%>%'"
        )).fetchall()

        updated = 0
        for book_id, description in rows:
            cleaned = html_to_text(description)
            if cleaned != description:
                db.execute(
                    text("UPDATE books SET description = :d WHERE id = :id"),
                    {"d": cleaned, "id": book_id},
                )
                updated += 1

        db.commit()
        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully! ({updated} descriptions cleaned)")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_migration_019_add_download_progress(db: Session, engine) -> None:
    """Add byte-progress tracking columns to the download queue."""
    migration_name = "019_add_download_progress"

    is_postgres = "postgresql" in str(engine.url)

    column_exists = False
    if is_postgres:
        result = db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='download_queue' AND column_name='progress_at'
        """))
        column_exists = result.fetchone() is not None
    else:
        result = db.execute(text("PRAGMA table_info(download_queue)"))
        columns = [col[1] for col in result.fetchall()]
        column_exists = "progress_at" in columns

    if column_exists:
        logger.debug("Download progress columns already exist, ensuring migration is marked as applied")
        if not has_migration_been_applied(db, migration_name):
            mark_migration_applied(db, migration_name)
        return

    if has_migration_been_applied(db, migration_name):
        logger.warning(f"Migration {migration_name} was marked as applied but columns don't exist - re-running")
        db.execute(text("DELETE FROM schema_migrations WHERE migration_name = :name"), {"name": migration_name})
        db.commit()

    logger.debug(f"Running migration: {migration_name}")

    try:
        db.execute(text("ALTER TABLE download_queue ADD COLUMN bytes_downloaded BIGINT"))
        db.execute(text("ALTER TABLE download_queue ADD COLUMN total_bytes BIGINT"))
        db.execute(text("ALTER TABLE download_queue ADD COLUMN progress_at TIMESTAMP"))
        db.execute(text("ALTER TABLE download_queue ADD COLUMN phase_started_at TIMESTAMP"))
        db.commit()
        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise


def run_all_pending_migrations(db: Session) -> None:
    """Run all pending migrations in order."""
    from .database import engine

    logger.debug("Checking for pending migrations...")

    # Ensure migration tracking table exists
    get_migration_table(engine)

    # List of migrations in order
    migrations = [
        run_migration_008_add_download_type,
        run_migration_009_add_cover_url,
        run_migration_010_add_purchased_at,
        run_migration_011_fix_download_type_enum,
        run_migration_012_fix_lowercase_download_types,
        run_migration_013_add_indexes_and_cascades,
        run_migration_014_add_user_notifications,
        run_migration_015_magic_links,
        run_migration_016_create_api_keys,
        run_migration_017_add_b2_keys,
        run_migration_018_strip_html_descriptions,
        run_migration_019_add_download_progress,
    ]

    for migration_func in migrations:
        try:
            migration_func(db, engine)
        except Exception as e:
            logger.error(f"Failed to run migration {migration_func.__name__}: {e}")
            # Don't stop on migration errors, continue with others
            continue

    logger.debug("Migration check complete")
