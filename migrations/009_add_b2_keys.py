"""Migration to add Backblaze B2 storage key columns.

Adds b2_audio_key and b2_cover_key to the books table. These record that a
file has been uploaded to B2; the upload sweep uses them to find work, and
the audiobook route uses b2_audio_key to issue a signed redirect.
"""

import os

from sqlalchemy import create_engine, text


def migrate(database_url: str = None) -> None:
    if database_url is None:
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://alima:changeme@postgres:5432/alima"
        )

    print("Connecting to database...")
    engine = create_engine(database_url)
    is_postgres = "postgresql" in database_url

    with engine.connect() as conn:
        try:
            if is_postgres:
                result = conn.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name='books' AND column_name='b2_audio_key'
                """))
                if result.fetchone():
                    print("B2 columns already exist — nothing to do")
                    return

                print("Adding b2_audio_key and b2_cover_key to books...")
                conn.execute(text("ALTER TABLE books ADD COLUMN b2_audio_key VARCHAR(512)"))
                conn.execute(text("ALTER TABLE books ADD COLUMN b2_cover_key VARCHAR(512)"))
            else:
                result = conn.execute(text("PRAGMA table_info(books)"))
                columns = [col[1] for col in result.fetchall()]

                if "b2_audio_key" in columns:
                    print("B2 columns already exist — nothing to do")
                    return

                print("Adding b2_audio_key and b2_cover_key to books...")
                conn.execute(text("ALTER TABLE books ADD COLUMN b2_audio_key VARCHAR(512)"))
                conn.execute(text("ALTER TABLE books ADD COLUMN b2_cover_key VARCHAR(512)"))

            conn.commit()
            print("Migration 009 completed successfully.")

        except Exception as e:
            print(f"Migration failed: {e}")
            conn.rollback()
            raise


if __name__ == "__main__":
    import sys
    migrate(sys.argv[1] if len(sys.argv) > 1 else None)
