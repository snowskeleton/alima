"""Migration to add purchased_at column to books table.

This migration adds the purchased_at datetime column to the books table
to store the purchase date from Audible.

Run this migration manually if you have an existing database.
For new databases, this column will be created automatically by init_db().
"""

from sqlalchemy import create_engine, text
from pathlib import Path
import os


def migrate(database_url: str = None) -> None:
    """
    Add purchased_at column to books table.

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
                # PostgreSQL: Check if column already exists
                result = conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name='books' AND column_name='purchased_at'
                """))

                if result.fetchone():
                    print("Column 'purchased_at' already exists in books table")
                    return

                print("Adding purchased_at column to books table...")
                conn.execute(text("""
                    ALTER TABLE books
                    ADD COLUMN purchased_at TIMESTAMP NULL
                """))
            else:
                # SQLite: Check if column exists
                result = conn.execute(text("PRAGMA table_info(books)"))
                columns = [col[1] for col in result.fetchall()]

                if "purchased_at" in columns:
                    print("Column 'purchased_at' already exists in books table")
                    return

                print("Adding purchased_at column to books table...")
                conn.execute(text("""
                    ALTER TABLE books
                    ADD COLUMN purchased_at DATETIME NULL
                """))

            conn.commit()
            print("Migration completed successfully!")
            print("Existing books will have NULL purchased_at until the next sync")

        except Exception as e:
            print(f"Migration failed: {e}")
            conn.rollback()
            raise


if __name__ == "__main__":
    import sys

    # Get database URL from command line or use default
    database_url = sys.argv[1] if len(sys.argv) > 1 else None
    migrate(database_url)
