"""Migration to add downloads_enabled column to audible_accounts table.

This migration adds the downloads_enabled boolean column to the audible_accounts table
with a default value of True.

Run this migration manually if you have an existing database.
For new databases, this column will be created automatically by init_db().
"""

import sqlite3
from pathlib import Path


def migrate(db_path: str = "data/db/alima.db") -> None:
    """
    Add downloads_enabled column to audible_accounts table.

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
        cursor.execute("PRAGMA table_info(audible_accounts)")
        columns = [col[1] for col in cursor.fetchall()]

        if "downloads_enabled" in columns:
            print("Column 'downloads_enabled' already exists in audible_accounts table")
            return

        # Add the column
        print("Adding downloads_enabled column to audible_accounts table...")
        cursor.execute(
            """
            ALTER TABLE audible_accounts
            ADD COLUMN downloads_enabled BOOLEAN DEFAULT 1 NOT NULL
            """
        )

        conn.commit()
        print("Migration completed successfully!")
        print("All existing accounts have downloads_enabled set to True (1)")

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
