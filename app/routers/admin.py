"""Admin routes for user and invite management."""

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import create_user, get_password_hash
from ..config import settings
from ..database import get_db
from ..dependencies import require_admin
from ..models import Feed, FeedType, Invite, PasswordReset, User, UserRole
from ..schemas import InviteResponse, UserResponse
from ..services.email_service import EmailService
from ..services.settings_service import SettingsService
from ..utils.tokens import generate_invite_token, generate_reset_token

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/invites", response_class=HTMLResponse)
async def list_invites(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Redirect to users page (invites are now managed there)."""
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.post("/invites/send", response_class=HTMLResponse)
async def send_invite(
    request: Request,
    email: str = Form(...),
    role: str = Form("user"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Send an email invite to a new user."""
    from ..utils.flash import flash

    # Check if user already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        flash(request, f"User with email '{email}' already exists", "error")
        return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

    # Check if there's already an active invite
    existing_invite = (
        db.query(Invite)
        .filter(Invite.email == email, Invite.used == False)
        .first()
    )
    if existing_invite:
        # Check if it's expired
        if existing_invite.expires_at > datetime.utcnow():
            flash(request, f"Active invite already exists for '{email}'", "error")
            return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)
        else:
            # Delete expired invite
            db.delete(existing_invite)
            db.commit()

    # Generate invite token
    invite_token = generate_invite_token()

    # Get invite expiration from database settings (with hardcoded default)
    invite_expire_days = 7  # Default: 7 days
    try:
        settings_service = SettingsService(db)
        db_expire = settings_service.get("invite_expire_days")
        if db_expire:
            invite_expire_days = int(db_expire)
    except Exception:
        pass  # Use hardcoded default if DB not available

    # Create invite
    invite = Invite(
        email=email,
        token=invite_token,
        role=UserRole(role),
        created_by=current_user.id,
        expires_at=datetime.utcnow() + timedelta(days=invite_expire_days),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    # Send invite email
    email_service = EmailService()
    email_sent = await email_service.send_invite_email(
        recipient_email=email,
        invite_token=invite_token,
        invited_by=current_user.email,
    )

    # If email not sent (SMTP not configured), log the invite URL
    if not email_sent:
        domain = SettingsService.get_domain(db)
        invite_url = f"{domain}/auth/accept-invite?token={invite_token}"
        print(f"\n{'='*60}")
        print(f"INVITE CREATED (SMTP not configured)")
        print(f"Email: {email}")
        print(f"Invite URL: {invite_url}")
        print(f"{'='*60}\n")
        flash(request, f"Invite created for '{email}' (check server logs for invite link)", "success")
    else:
        flash(request, f"Invite sent to '{email}'", "success")

    # Redirect back to users page
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/create", response_class=HTMLResponse)
async def create_user_direct(
    email: str = Form(...),
    role: str = Form("user"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Create a new user directly without sending an invite.

    User is created with a random password. Admin can then send
    a password reset link which acts as the invitation.
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{email}' already exists",
        )

    # Generate random password (user will reset it via link)
    random_password = secrets.token_urlsafe(16)

    # Create user
    user = create_user(db, email, random_password, role=role)

    # Create default "My Library" feed for the new user
    default_feed = Feed(
        user_id=user.id,
        name="My Library",
        description="My personal audiobook collection",
        feed_type=FeedType.SMART,
        filter_criteria=None,  # All books
        is_public=False,
        slug=f"my-library-{generate_invite_token(length=8)}",
    )
    db.add(default_feed)
    db.commit()
    db.refresh(user)

    # Redirect to user creation success page
    return RedirectResponse(
        url=f"/admin/users/{user.id}/created",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/users/{user_id}/created", response_class=HTMLResponse)
async def user_created_page(
    request: Request,
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Display user creation success page with password reset option."""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )

    # Generate a password reset token to show the link
    reset_token = generate_reset_token()
    domain = SettingsService.get_domain(db)
    reset_url = f"{domain}/auth/reset-password?token={reset_token}"

    # Store token in database (expires in 24 hours)
    password_reset = PasswordReset(
        user_id=user.id,
        token=reset_token,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(password_reset)
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="admin/user_created.html",
        context={
            "current_user": current_user,
            "new_user": user,
            "reset_url": reset_url,
            "reset_token": reset_token,
        },
    )


@router.post("/users/{user_id}/send-reset")
async def send_password_reset(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Send a password reset email to a user."""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        return {"error": "User not found"}

    # Generate reset token
    reset_token = generate_reset_token()

    # Store token in database (expires in 24 hours)
    password_reset = PasswordReset(
        user_id=user.id,
        token=reset_token,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(password_reset)
    db.commit()

    # Send password reset email
    email_service = EmailService()
    email_sent = await email_service.send_password_reset_email(
        recipient_email=user.email,
        reset_token=reset_token,
    )

    # If email not sent (SMTP not configured), log the reset URL
    if not email_sent:
        domain = SettingsService.get_domain(db)
        reset_url = f"{domain}/auth/reset-password?token={reset_token}"
        print(f"\n{'='*60}")
        print(f"PASSWORD RESET (SMTP not configured)")
        print(f"Email: {user.email}")
        print(f"Reset URL: {reset_url}")
        print(f"{'='*60}\n")

    return {"success": True, "message": f"Password reset sent to {user.email}", "email_sent": email_sent}


@router.delete("/invites/{invite_id}")
async def revoke_invite(
    invite_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Revoke (delete) an unused invite."""
    invite = db.query(Invite).filter(Invite.id == invite_id).first()
    if not invite:
        return {"error": "Invite not found"}

    if invite.used:
        return {"error": "Cannot revoke an invite that has already been used"}

    invite_email = invite.email
    db.delete(invite)
    db.commit()

    return {"success": True, "message": f"Invite for '{invite_email}' revoked successfully"}


@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    sort: str = "created_desc",
):
    """List all users in the system."""
    # Parse sort parameter
    sort_field, sort_dir = sort.rsplit("_", 1) if "_" in sort else ("created", "desc")

    # Build users query with sorting
    users_query = db.query(User)
    if sort_field == "email":
        users_query = users_query.order_by(User.email.asc() if sort_dir == "asc" else User.email.desc())
    elif sort_field == "role":
        users_query = users_query.order_by(User.role.asc() if sort_dir == "asc" else User.role.desc())
    elif sort_field == "last_login":
        users_query = users_query.order_by(User.last_login.asc() if sort_dir == "asc" else User.last_login.desc())
    else:  # created
        users_query = users_query.order_by(User.created_at.asc() if sort_dir == "asc" else User.created_at.desc())

    users = users_query.all()

    # Get pending invites
    invites = db.query(Invite).filter(Invite.used == False).order_by(Invite.created_at.desc()).all()

    from ..utils.flash import get_flashed_messages

    return templates.TemplateResponse(
        request=request,
        name="admin/users.html",
        context={
            "current_user": current_user,
            "users": users,
            "invites": invites,
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

    # Don't allow changing own role
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

    # Don't allow deleting yourself
    if user.id == current_user.id:
        return {"error": "Cannot delete your own account"}

    user_email = user.email
    db.delete(user)
    db.commit()

    return {"success": True, "message": f"User '{user_email}' deleted successfully"}


@router.post("/sync/force-refresh-metadata")
async def force_refresh_metadata(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Force refresh all book metadata from Audible.
    This will update ALL fields including purchase dates, even if already set.

    Useful when Audible API returned incorrect data during initial sync.
    """
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
