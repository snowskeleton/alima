"""Migration to add download_enabled column to books table.

This migration adds the download_enabled boolean column to the books table
with a default value of True.

Run this migration manually if you have an existing database.
For new databases, this column will be created automatically by init_db().
"""

import sqlite3
from pathlib import Path


def migrate(db_path: str = "data/db/alima.db") -> None:
    """
    Add download_enabled column to books table.

    Args:
        db_path: Path to the SQLite database file
    """
    # Check if database exists
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(books)")
        columns = [col[1] for col in cursor.fetchall()]

        if "download_enabled" in columns:
            print("Column 'download_enabled' already exists in books table")
            return

        # Add the column
        print("Adding download_enabled column to books table...")
        cursor.execute(
            """
            ALTER TABLE books
            ADD COLUMN download_enabled BOOLEAN DEFAULT 1 NOT NULL
            """
        )

        conn.commit()
        print("Migration completed successfully!")
        print("All existing books have download_enabled set to True (1)")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    # Get database path from command line or use default
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/db/alima.db"
    migrate(db_path)
