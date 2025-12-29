"""Migration to add download_type column to download_queue table.

This migration adds the download_type enum column to the download_queue table
with a default value of 'book' to support both book and cover downloads.

Run this migration manually if you have an existing database.
For new databases, this column will be created automatically by init_db().
"""

from sqlalchemy import create_engine, text
from pathlib import Path
import os


def migrate(database_url: str = None) -> None:
    """
    Add download_type column to download_queue table.

    Args:
        database_url: Database connection string (PostgreSQL or SQLite)
    """
    # Get database URL from environment or use default
    if database_url is None:
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://alima:changeme@postgres:5432/alima"
        )

    print(f"Connecting to database...")
    engine = create_engine(database_url)

    with engine.connect() as conn:
        try:
            # Check if we're using PostgreSQL or SQLite
            is_postgres = "postgresql" in database_url

            if is_postgres:
                # PostgreSQL: Create enum type first, then add column
                print("Creating downloadtype enum type...")
                conn.execute(text("""
                    DO $$ BEGIN
                        CREATE TYPE downloadtype AS ENUM ('book', 'cover');
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """))
                conn.commit()

                # Check if column already exists
                result = conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name='download_queue' AND column_name='download_type'
                """))

                if result.fetchone():
                    print("Column 'download_type' already exists in download_queue table")
                    return

                print("Adding download_type column to download_queue table...")
                conn.execute(text("""
                    ALTER TABLE download_queue
                    ADD COLUMN download_type downloadtype DEFAULT 'book' NOT NULL
                """))
            else:
                # SQLite: Check if column exists
                result = conn.execute(text("PRAGMA table_info(download_queue)"))
                columns = [col[1] for col in result.fetchall()]

                if "download_type" in columns:
                    print("Column 'download_type' already exists in download_queue table")
                    return

                print("Adding download_type column to download_queue table...")
                conn.execute(text("""
                    ALTER TABLE download_queue
                    ADD COLUMN download_type VARCHAR(10) DEFAULT 'book' NOT NULL
                """))

            conn.commit()
            print("Migration completed successfully!")
            print("All existing queue entries have download_type set to 'book'")

        except Exception as e:
            print(f"Migration failed: {e}")
            conn.rollback()
            raise


if __name__ == "__main__":
    import sys

    # Get database URL from command line or use default
    database_url = sys.argv[1] if len(sys.argv) > 1 else None
    migrate(database_url)
