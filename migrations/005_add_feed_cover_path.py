"""Migration to add cover_image_path column to feeds table.

This migration adds the cover_image_path text column to the feeds table
to store the path to custom feed cover artwork.

Run this migration manually if you have an existing database.
For new databases, this column will be created automatically by init_db().
"""

import sqlite3
from pathlib import Path


def migrate(db_path: str = "data/db/alima.db") -> None:
    """
    Add cover_image_path column to feeds table.

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
        cursor.execute("PRAGMA table_info(feeds)")
        columns = [col[1] for col in cursor.fetchall()]

        if "cover_image_path" in columns:
            print("Column 'cover_image_path' already exists in feeds table")
            return

        # Add the column
        print("Adding cover_image_path column to feeds table...")
        cursor.execute("""
            ALTER TABLE feeds
            ADD COLUMN cover_image_path TEXT
        """)

        conn.commit()
        print("Migration completed successfully!")
        print("Added cover_image_path column to feeds table")

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
