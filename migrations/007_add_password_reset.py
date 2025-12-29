"""Migration to add password_resets table.

This migration creates the password_resets table to store password reset tokens.
This supports the simplified user creation flow where admins create users
and send password reset links as invitations.

Run this migration manually if you have an existing database.
For new databases, this table will be created automatically by init_db().
"""

import sqlite3
from pathlib import Path


def migrate(db_path: str = "data/db/alima.db") -> None:
    """
    Create password_resets table.

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
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='password_resets'
        """)

        if cursor.fetchone():
            print("Table 'password_resets' already exists")
            return

        # Create the table
        print("Creating password_resets table...")
        cursor.execute("""
            CREATE TABLE password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token VARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                used BOOLEAN DEFAULT 0 NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Create index on token for fast lookups
        cursor.execute("""
            CREATE UNIQUE INDEX idx_password_resets_token
            ON password_resets(token)
        """)

        # Create index on user_id
        cursor.execute("""
            CREATE INDEX idx_password_resets_user_id
            ON password_resets(user_id)
        """)

        conn.commit()
        print("Migration completed successfully!")
        print("Created password_resets table with indexes")

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
