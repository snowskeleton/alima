#!/usr/bin/env python3
"""Command-line interface for Alima administration."""

import sys
from pathlib import Path

import click
import httpx
from sqlalchemy.orm import Session

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.auth import create_magic_link, create_user
from app.database import SessionLocal, init_db
from app.models import User, UserRole

# API base URL for CLI commands
DEFAULT_API_URL = "http://localhost:8000"


def get_db() -> Session:
    """Get database session for CLI commands (only for bootstrap operations)."""
    return SessionLocal()


def get_api_client(api_url: str = DEFAULT_API_URL) -> httpx.Client:
    """Get HTTP client for API calls."""
    return httpx.Client(base_url=api_url, timeout=30.0)


@click.group()
@click.option('--api-url', default=DEFAULT_API_URL, envvar='ALIMA_API_URL',
              help='API base URL (default: http://localhost:8000)')
@click.pass_context
def cli(ctx, api_url):
    """Alima CLI - Administrative commands for Alima."""
    ctx.ensure_object(dict)
    ctx.obj['API_URL'] = api_url


@cli.command()
@click.option("--email", prompt=True, help="Admin email address")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="Admin password")
def create_admin(email: str, password: str):
    """Create a new admin user."""
    db = get_db()
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            click.echo(f"❌ Error: User with email '{email}' already exists")
            return

        # Create admin user
        user = create_user(db, email, password, role="admin")
        click.echo(f"✓ Admin user created successfully: {user.email}")
        click.echo(f"  User ID: {user.id}")
        click.echo(f"  Role: {user.role.value}")

    except Exception as e:
        click.echo(f"❌ Error creating admin user: {e}")
    finally:
        db.close()


@cli.command()
@click.option("--email", prompt=True, help="User email address")
def send_login_link(email: str):
    """Generate a magic login link for a user."""
    db = get_db()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            click.echo(f"❌ Error: User with email '{email}' not found")
            return

        token = create_magic_link(db, email)
        click.echo(f"✓ Magic link created for: {user.email}")
        click.echo(f"  Login URL: /auth/magic-link?token={token}")
        click.echo(f"  (Expires in 15 minutes)")

    except Exception as e:
        click.echo(f"❌ Error creating magic link: {e}")
        db.rollback()
    finally:
        db.close()


@cli.command()
def migrate_db():
    """Initialize/migrate the database."""
    try:
        click.echo("Initializing database...")
        init_db()
        click.echo("✓ Database initialized successfully")
    except Exception as e:
        click.echo(f"❌ Error initializing database: {e}")


@cli.command()
def list_users():
    """List all users in the system."""
    db = get_db()
    try:
        users = db.query(User).all()
        if not users:
            click.echo("No users found")
            return

        click.echo("\nUsers:")
        click.echo("-" * 70)
        for user in users:
            last_login = user.last_login.strftime("%Y-%m-%d %H:%M:%S") if user.last_login else "Never"
            click.echo(f"ID: {user.id:3d} | {user.email:30s} | Role: {user.role.value:5s} | Last login: {last_login}")
        click.echo("-" * 70)
        click.echo(f"Total: {len(users)} users")

    except Exception as e:
        click.echo(f"❌ Error listing users: {e}")
    finally:
        db.close()


@cli.command()
@click.option("--email", prompt=True, help="User email address")
@click.option("--role", type=click.Choice(["admin", "user"]), prompt=True, help="New role")
def change_role(email: str, role: str):
    """Change a user's role."""
    db = get_db()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            click.echo(f"❌ Error: User with email '{email}' not found")
            return

        old_role = user.role.value
        user.role = UserRole(role)
        db.commit()
        click.echo(f"✓ Role changed for {user.email}: {old_role} → {role}")

    except Exception as e:
        click.echo(f"❌ Error changing role: {e}")
        db.rollback()
    finally:
        db.close()


@cli.command()
@click.option("--email", prompt=True, help="User email to delete")
@click.confirmation_option(prompt="Are you sure you want to delete this user?")
def delete_user(email: str):
    """Delete a user from the system."""
    db = get_db()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            click.echo(f"❌ Error: User with email '{email}' not found")
            return

        db.delete(user)
        db.commit()
        click.echo(f"✓ User deleted: {email}")

    except Exception as e:
        click.echo(f"❌ Error deleting user: {e}")
        db.rollback()
    finally:
        db.close()


@cli.command()
@click.option("--username", required=True, help="Audible account username")
@click.option("--auth-file", required=True, help="Path to Audible auth file (will be uploaded)")
@click.option("--activation-bytes", required=True, help="Activation bytes for decryption")
@click.option("--marketplace", default="US", help="Marketplace code (US, UK, DE, etc.)")
@click.pass_context
def import_account(ctx, username: str, auth_file: str, activation_bytes: str, marketplace: str):
    """Import an Audible account via API."""
    api_url = ctx.obj['API_URL']

    try:
        # Check if file exists locally
        auth_file_path = Path(auth_file)
        if not auth_file_path.exists():
            click.echo(f"❌ Error: Auth file not found at {auth_file_path}")
            return

        with get_api_client(api_url) as client:
            # Upload auth file and create account via API
            # For now, we'll use the direct database approach since we need file upload
            # TODO: Create proper file upload API endpoint
            click.echo("⚠️  Note: Account import requires direct database access for now.")
            click.echo("    Use the web GUI to add accounts with file upload.")
            click.echo(f"\n    OR manually copy {auth_file} to data/audible_auth/")
            click.echo(f"    Then use: POST {api_url}/admin/accounts/add")

    except Exception as e:
        click.echo(f"❌ Error: {e}")


@cli.command()
@click.option("--account-id", type=int, help="Sync specific account by ID")
@click.pass_context
def sync(ctx, account_id: int | None):
    """Trigger a manual library sync via API."""
    api_url = ctx.obj['API_URL']

    if not account_id:
        click.echo("❌ Error: --account-id is required")
        click.echo("   Use the web GUI at /admin/accounts to see account IDs")
        return

    try:
        with get_api_client(api_url) as client:
            click.echo(f"Syncing account {account_id}...")

            # Call the sync API endpoint
            response = client.post(
                f"/admin/accounts/{account_id}/sync",
                # TODO: Add authentication (API key or session)
            )

            if response.status_code == 200:
                data = response.json()
                stats = data.get('stats', {})
                click.echo(f"\n✓ Sync completed:")
                click.echo(f"  Total books: {stats.get('total', 0)}")
                click.echo(f"  New books: {stats.get('new', 0)}")
                click.echo(f"  Updated books: {stats.get('updated', 0)}")
                click.echo(f"  Queued downloads: {stats.get('queued', 0)}")
            else:
                click.echo(f"❌ Error: API returned {response.status_code}")
                click.echo(f"   {response.text}")

    except httpx.ConnectError:
        click.echo(f"❌ Error: Could not connect to API at {api_url}")
        click.echo("   Make sure the server is running: uvicorn app.main:app")
    except Exception as e:
        click.echo(f"❌ Error: {e}")


@cli.command()
@click.option("--limit", type=int, default=None, help="Maximum books to upload (default: all)")
@click.option("--concurrent", type=int, default=2, help="Parallel upload workers")
@click.option("--dry-run", is_flag=True, help="List what would be uploaded without uploading")
def backfill_b2(limit: int, concurrent: int, dry_run: bool):
    """Upload existing audiobooks and covers to Backblaze B2.

    Uploads any book that has a local file but no B2 key yet. Safe to re-run —
    already-uploaded books are skipped. This is the same operation the scheduler
    performs automatically; use this to migrate an existing library in one pass.
    """
    from app.services.b2_upload import B2UploadService
    from app.services.storage import get_storage_service

    if not get_storage_service():
        click.echo("❌ B2 is not configured or not enabled.")
        click.echo("   Set B2_ENABLED=true and the B2_* credentials in your .env")
        return

    db = get_db()
    try:
        service = B2UploadService(db)
        pending = service.find_pending(limit=limit)

        if not pending:
            click.echo("✓ Nothing to upload — every book with a local file is already in B2.")
            return

        click.echo(f"Found {len(pending)} book(s) needing upload:\n")
        for book in pending[:20]:
            needs = []
            if not book.b2_audio_key:
                needs.append("audio")
            if book.cover_image_path and not book.b2_cover_key:
                needs.append("cover")
            click.echo(f"  [{book.id}] {book.title} ({', '.join(needs)})")
        if len(pending) > 20:
            click.echo(f"  ... and {len(pending) - 20} more")

        if dry_run:
            click.echo("\n(dry run — nothing uploaded)")
            return

        if not click.confirm(f"\nUpload {len(pending)} book(s) to B2?"):
            click.echo("Aborted.")
            return

        click.echo("")
        with click.progressbar(length=len(pending), label="Uploading") as bar:
            def on_progress(book, stats):
                bar.update(1)

            stats = service.process_pending(
                limit=limit,
                max_concurrent=concurrent,
                progress_callback=on_progress,
            )

        click.echo(f"\n✓ Uploaded: {stats['uploaded']}")
        if stats["failed"]:
            click.echo(f"❌ Failed: {stats['failed']} (see logs; re-run to retry)")

    finally:
        db.close()


# TODO: Add more commands as we progress through phases
# - scan-audiobooks: Scan and import existing audiobooks
# - set-mode: Set replication mode
# - pair-with-master: Pair as slave
# - generate-slave-key: Generate pairing key for slave
# - replicate-now: Manual replication
# - unpair: Disconnect from master/slave


if __name__ == "__main__":
    cli()
