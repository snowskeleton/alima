"""Migration to add system feeds support to feeds table.

This migration:
1. Makes user_id nullable (to allow system-owned feeds)
2. Adds is_system boolean column (to mark system feeds as undeletable)

Note: SQLite doesn't support ALTER COLUMN, so we recreate the table.

Run this migration manually if you have an existing database.
For new databases, these columns will be created automatically by init_db().
"""

import sqlite3
from pathlib import Path


def migrate(db_path: str = "data/db/alima.db") -> None:
    """
    Recreate feeds table with nullable user_id and is_system column.

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
        # Check if is_system column already exists
        cursor.execute("PRAGMA table_info(feeds)")
        columns = [col[1] for col in cursor.fetchall()]

        if "is_system" in columns:
            print("Column 'is_system' already exists in feeds table")
            return

        print("Recreating feeds table with nullable user_id and is_system column...")

        # Create new feeds table with desired schema
        cursor.execute("""
            CREATE TABLE feeds_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                feed_type VARCHAR(50) NOT NULL,
                filter_criteria JSON,
                is_public BOOLEAN DEFAULT 1,
                is_system BOOLEAN DEFAULT 0,
                slug VARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Copy data from old table
        cursor.execute("""
            INSERT INTO feeds_new
                (id, user_id, name, description, feed_type, filter_criteria,
                 is_public, is_system, slug, created_at, updated_at)
            SELECT
                id, user_id, name, description, feed_type, filter_criteria,
                is_public, 0 as is_system, slug, created_at, updated_at
            FROM feeds
        """)

        # Drop old table
        cursor.execute("DROP TABLE feeds")

        # Rename new table
        cursor.execute("ALTER TABLE feeds_new RENAME TO feeds")

        # Recreate indexes
        cursor.execute("CREATE UNIQUE INDEX idx_feeds_slug ON feeds(slug)")

        conn.commit()
        print("Migration completed successfully!")
        print("- user_id is now nullable")
        print("- Added is_system column (default: False)")

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
