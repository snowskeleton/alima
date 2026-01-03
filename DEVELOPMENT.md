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

## CSRF Protection for Forms

### Pattern: All POST forms MUST have CSRF protection

**CRITICAL:** The application uses `starlette-csrf` which ONLY validates CSRF tokens in request headers (NOT form fields).

### For pages that extend base.html

If your template extends `base.html`, CSRF protection is automatic:
1. Add `{% from "_csrf.html" import csrf_token %}` at the top
2. Add `{{ csrf_token(request) }}` inside each `<form>` tag
3. The JavaScript in `base.html` automatically intercepts form submissions and adds the CSRF header

### For standalone pages (login, register, accept_invite, etc.)

Standalone pages don't extend `base.html`, so they need manual CSRF setup:

1. **Add CSRF meta tag in `<head>`:**
```html
<meta name="csrf-token" content="{{ request.cookies.get('alima_csrf', '') }}">
```

2. **Add CSRF token macro to form:**
```html
{% from "_csrf.html" import csrf_token %}
<form method="POST" action="/your-endpoint">
    {{ csrf_token(request) }}
    <!-- form fields -->
</form>
```

3. **Add CSRF JavaScript before `</body>`:**
```html
<script>
    // Get CSRF token from meta tag
    function getCsrfToken() {
        const token = document.querySelector('meta[name="csrf-token"]');
        return token ? token.getAttribute('content') : '';
    }

    // Add CSRF token to fetch request headers
    function addCsrfToFetch(options = {}) {
        const token = getCsrfToken();
        if (!options.headers) {
            options.headers = {};
        }
        options.headers['x-csrf-token'] = token;
        return options;
    }

    // Auto-intercept form submission and convert to fetch with CSRF header
    document.addEventListener('DOMContentLoaded', function() {
        const form = document.querySelector('form');
        if (form && form.method.toUpperCase() === 'POST') {
            form.addEventListener('submit', function(e) {
                e.preventDefault();
                const formData = new FormData(form);
                const action = form.action;

                fetch(action, addCsrfToFetch({
                    method: 'POST',
                    body: formData,
                }))
                .then(response => {
                    if (response.redirected) {
                        window.location.href = response.url;
                    } else if (response.ok) {
                        window.location.reload();
                    } else {
                        return response.text().then(text => {
                            alert('Request failed: ' + response.statusText);
                        });
                    }
                })
                .catch(error => {
                    console.error('Request error:', error);
                    alert('Request failed. Please try again.');
                });
            });
        }
    });
</script>
```

### Checklist: Verifying CSRF Protection

When adding or modifying forms, verify:

1. **Find all templates with forms:**
   ```bash
   find app/templates -name "*.html" -exec grep -l '<form' {} \;
   ```

2. **For each template with a POST form:**
   - If it extends `base.html`: ✅ Has `{{ csrf_token(request) }}` in form
   - If it's standalone: ✅ Has CSRF meta tag AND JavaScript

3. **Test the form:**
   - Submit should work without 403 CSRF errors
   - Check browser console for errors

### Why This Mistake Happened

**Root cause:** Standalone authentication pages (login, register, accept_invite) don't extend `base.html`, so they were missing the automatic CSRF JavaScript interception despite having the CSRF token macro in their forms.

**Lesson:** Always check for standalone pages when implementing security features that rely on `base.html`.

## Password Hashing

### Current Implementation: Argon2id Only

The application uses **Argon2id** exclusively for password hashing (via `argon2-cffi`), which is:
- The OWASP-recommended algorithm
- Winner of the Password Hashing Competition
- More secure than bcrypt
- No password length limits (bcrypt has a 72-byte limit)
- Actively maintained

### Migration from passlib/bcrypt

Users with old bcrypt password hashes can reset their passwords via the "Forgot your password?" link on the login page. No backward compatibility is maintained to keep the codebase simple and secure.

### Code Location

All password hashing logic is in `/app/auth.py`:
- `get_password_hash(password)` - Hash a password using Argon2id
- `verify_password(plain, hashed)` - Verify an Argon2 password hash
- `authenticate_user()` - Authenticates users and auto-rehashes if Argon2 parameters change

### Why We Replaced passlib

The old `passlib` library is unmaintained and has compatibility issues with modern bcrypt versions (the `AttributeError: module 'bcrypt' has no attribute '__about__'` error). We replaced it with `argon2-cffi` for a cleaner, more secure implementation.

## Other Development Patterns

(Add more patterns here as they are discovered)
