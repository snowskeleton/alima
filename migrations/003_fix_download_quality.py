"""Migration to fix download_quality settings from Extreme to High.

The Audible API only accepts "High" and "Normal" as quality values.
This migration updates any settings with "Extreme" to "High".
"""

import sqlite3
from pathlib import Path


def migrate(db_path: str = "data/db/alima.db") -> None:
    """
    Update download_quality from Extreme to High.

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
        # Check if server_settings table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='server_settings'"
        )
        if not cursor.fetchone():
            print("server_settings table does not exist, skipping migration")
            return

        # Update any "Extreme" download_quality settings to "High"
        cursor.execute(
            """
            UPDATE server_settings
            SET value = 'High'
            WHERE key = 'download_quality' AND value = 'Extreme'
            """
        )

        rows_updated = cursor.rowcount
        conn.commit()

        if rows_updated > 0:
            print(f"Updated {rows_updated} download_quality setting(s) from Extreme to High")
        else:
            print("No Extreme quality settings found to update")

        print("Migration completed successfully!")

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
