# Development Guide

This document contains important patterns and conventions for developing Alima.

## Database Migrations

### Pattern: DO NOT create standalone migration scripts

**CRITICAL:** This project does NOT use standalone migration files in the `/migrations` directory for runtime migrations.

### Correct Pattern for Database Schema Changes

When you need to add or modify database schema:

1. **Update the model** in `/app/models.py` with the new field
2. **Add a migration function** in `/app/migrations_runner.py`:
   - Create a new function `run_migration_XXX_description(db: Session, engine) -> None`
   - Follow the existing pattern (check if column exists, handle both PostgreSQL and SQLite)
   - Add the function to the `migrations` list in `run_all_pending_migrations()`

3. **Migration will run automatically** on app startup

### Example Migration Function Structure

```python
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
        logger.info(f"Column receive_notifications already exists, ensuring migration is marked as applied")
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

    logger.info(f"Running migration: {migration_name}")

    try:
        logger.info("Adding receive_notifications column to users table...")
        if is_postgres:
            db.execute(text("""
                ALTER TABLE users
                ADD COLUMN receive_notifications BOOLEAN DEFAULT FALSE NOT NULL
            """))
        else:
            db.execute(text("""
                ALTER TABLE users
                ADD COLUMN receive_notifications BOOLEAN DEFAULT 0 NOT NULL
            """))

        db.commit()
        mark_migration_applied(db, migration_name)
        logger.info(f"Migration {migration_name} completed successfully!")

    except Exception as e:
        logger.error(f"Migration {migration_name} failed: {e}", exc_info=True)
        db.rollback()
        raise
```

### Then add to the migrations list:

```python
def run_all_pending_migrations(db: Session) -> None:
    """Run all pending migrations in order."""
    # ...

    migrations = [
        run_migration_008_add_download_type,
        run_migration_009_add_cover_url,
        # ... other migrations ...
        run_migration_014_add_user_notifications,  # Add your new migration here
    ]
```

### What About the /migrations Directory?

The `/migrations` directory contains **standalone migration scripts** that can be run manually via command line for database maintenance. These are NOT automatically run on startup.

These scripts are useful for:
- One-time manual database fixes
- Historical reference
- Running migrations outside the normal app startup

But for normal development, **always use the migrations_runner.py pattern**.

## Other Development Patterns

(Add more patterns here as they are discovered)
