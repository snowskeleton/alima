"""Admin routes for user management."""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import create_magic_link, create_user
from ..config import settings
from ..database import get_db
from ..dependencies import require_admin
from ..models import ApiKey, Feed, FeedType, User, UserRole
from ..services.email_service import EmailService
from ..services.settings_service import SettingsService
from ..utils.tokens import generate_invite_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/invites", response_class=HTMLResponse)
async def list_invites(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Redirect to users page."""
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.post("/invites/send", response_class=HTMLResponse)
async def send_invite(
    request: Request,
    email: str = Form(...),
    role: str = Form("user"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user and send them a magic link login email."""
    from ..utils.flash import flash

    # Check if user already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        flash(request, f"User with email '{email}' already exists", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    # Create the user account directly
    user = create_user(db, email, role=role)

    # Create default "My Library" feed for the new user
    default_feed = Feed(
        user_id=user.id,
        name="My Library",
        description="My personal audiobook collection",
        feed_type=FeedType.SMART,
        filter_criteria=None,
        is_public=False,
        slug=f"my-library-{generate_invite_token(length=8)}",
    )
    db.add(default_feed)
    db.commit()

    # Generate magic link and send email
    token = create_magic_link(db, email)

    email_service = EmailService()
    email_sent = await email_service.send_magic_link_email(
        recipient_email=email,
        magic_link_token=token,
    )

    if not email_sent:
        domain = SettingsService.get_domain(db)
        magic_url = f"{domain}/auth/magic-link?token={token}"
        print(f"\n{'='*60}")
        print(f"USER CREATED (SMTP not configured)")
        print(f"Email: {email}")
        print(f"Login URL: {magic_url}")
        print(f"{'='*60}\n")
        flash(request, f"User '{email}' created (check server logs for login link)", "success")
    else:
        flash(request, f"User '{email}' created and login link sent", "success")

    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/create", response_class=HTMLResponse)
async def create_user_direct(
    request: Request,
    email: str = Form(...),
    role: str = Form("user"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user and send them a magic link."""
    from ..utils.flash import flash

    # Check if user already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        flash(request, f"User with email '{email}' already exists", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    # Create user (no password)
    user = create_user(db, email, role=role)

    # Create default "My Library" feed for the new user
    default_feed = Feed(
        user_id=user.id,
        name="My Library",
        description="My personal audiobook collection",
        feed_type=FeedType.SMART,
        filter_criteria=None,
        is_public=False,
        slug=f"my-library-{generate_invite_token(length=8)}",
    )
    db.add(default_feed)
    db.commit()

    # Generate magic link and send email
    token = create_magic_link(db, email)

    email_service = EmailService()
    email_sent = await email_service.send_magic_link_email(
        recipient_email=email,
        magic_link_token=token,
    )

    if not email_sent:
        domain = SettingsService.get_domain(db)
        magic_url = f"{domain}/auth/magic-link?token={token}"
        print(f"\n{'='*60}")
        print(f"USER CREATED (SMTP not configured)")
        print(f"Email: {email}")
        print(f"Login URL: {magic_url}")
        print(f"{'='*60}\n")
        flash(request, f"User '{email}' created (check server logs for login link)", "success")
    else:
        flash(request, f"User '{email}' created and login link sent", "success")

    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{user_id}/send-login-link")
async def send_login_link(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Send a magic link login email to a user."""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        return {"error": "User not found"}

    # Generate magic link
    token = create_magic_link(db, user.email)

    # Send email
    email_service = EmailService()
    email_sent = await email_service.send_magic_link_email(
        recipient_email=user.email,
        magic_link_token=token,
    )

    if not email_sent:
        domain = SettingsService.get_domain(db)
        magic_url = f"{domain}/auth/magic-link?token={token}"
        print(f"\n{'='*60}")
        print(f"LOGIN LINK (SMTP not configured)")
        print(f"Email: {user.email}")
        print(f"Login URL: {magic_url}")
        print(f"{'='*60}\n")

    return {"success": True, "message": f"Login link sent to {user.email}", "email_sent": email_sent}


@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    sort: str = "created_desc",
):
    """List all users in the system."""
    sort_field, sort_dir = sort.rsplit("_", 1) if "_" in sort else ("created", "desc")

    users_query = db.query(User)
    if sort_field == "email":
        users_query = users_query.order_by(User.email.asc() if sort_dir == "asc" else User.email.desc())
    elif sort_field == "role":
        users_query = users_query.order_by(User.role.asc() if sort_dir == "asc" else User.role.desc())
    elif sort_field == "last_login":
        users_query = users_query.order_by(User.last_login.asc() if sort_dir == "asc" else User.last_login.desc())
    else:
        users_query = users_query.order_by(User.created_at.asc() if sort_dir == "asc" else User.created_at.desc())

    users = users_query.all()

    from ..utils.flash import get_flashed_messages

    return templates.TemplateResponse(
        request=request,
        name="admin/users.html",
        context={
            "current_user": current_user,
            "users": users,
            "current_sort": sort,
            "now": datetime.utcnow(),
            "messages": get_flashed_messages(request),
        },
    )


@router.post("/users/{user_id}/change-role")
async def change_user_role(
    user_id: int,
    role: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Change a user's role."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "User not found"}

    if user.id == current_user.id:
        return {"error": "Cannot change your own role"}

    user.role = UserRole(role)
    db.commit()
    db.refresh(user)

    return {"success": True, "message": f"Role changed to {role} for {user.email}"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a user from the system."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "User not found"}

    if user.id == current_user.id:
        return {"error": "Cannot delete your own account"}

    user_email = user.email
    db.delete(user)
    db.commit()

    return {"success": True, "message": f"User '{user_email}' deleted successfully"}


@router.post("/users/{user_id}/toggle-notifications")
async def toggle_user_notifications(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Toggle email notifications for a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "User not found", "success": False}

    if user.role != UserRole.ADMIN:
        return {"error": "Only admin users can receive notifications", "success": False}

    body = await request.json()
    enabled = body.get("enabled", False)

    user.receive_notifications = enabled
    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "message": f"Notifications {'enabled' if enabled else 'disabled'} for {user.email}"
    }


@router.post("/sync/force-refresh-metadata")
async def force_refresh_metadata(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Force refresh all book metadata from Audible."""
    from ..services.audible_sync import AudibleSyncService

    try:
        sync_service = AudibleSyncService(db)
        stats = sync_service.force_refresh_all_metadata()

        return {
            "success": True,
            "message": "Metadata refresh completed",
            "stats": stats,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/api-keys", response_class=HTMLResponse)
async def list_api_keys(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all API keys for the current admin user."""
    from ..utils.flash import get_flashed_messages

    api_keys = db.query(ApiKey).filter(ApiKey.user_id == current_user.id).order_by(ApiKey.created_at.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="admin/api_keys.html",
        context={
            "current_user": current_user,
            "api_keys": api_keys,
            "messages": get_flashed_messages(request),
        },
    )


@router.post("/api-keys/create")
async def create_api_key(
    request: Request,
    name: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Generate a new API key."""
    raw_key = secrets.token_urlsafe(32)
    key_prefix = raw_key[:8]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = ApiKey(
        user_id=current_user.id,
        name=name,
        key_prefix=key_prefix,
        key_hash=key_hash,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    logger.info(f"API key created: '{name}' by {current_user.email}")

    return JSONResponse(content={
        "success": True,
        "key": raw_key,
        "key_id": api_key.id,
        "name": api_key.name,
        "prefix": key_prefix,
    })


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Revoke an API key."""
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == current_user.id,
    ).first()

    if not api_key:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "API key not found"},
        )

    key_name = api_key.name
    db.delete(api_key)
    db.commit()

    logger.info(f"API key revoked: '{key_name}' by {current_user.email}")

    return JSONResponse(content={"success": True, "message": f"API key '{key_name}' revoked"})
