"""Authentication routes - magic link login, registration, logout."""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..auth import (
    create_access_token,
    create_magic_link,
    create_user,
    update_last_login,
    verify_magic_link,
)
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user, get_optional_user
from ..models import User
from ..services.email_service import EmailService
from ..services.settings_service import SettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")

# Rate limiter for authentication endpoints
limiter = Limiter(key_func=get_remote_address)


def get_session_expiration_hours() -> int:
    """Get session expiration time in hours from settings with caching."""
    from ..utils.settings_cache import get_cached_setting
    return get_cached_setting("session_expire_hours", 168, int)


def _create_session_response(user: User, redirect_url: str = "/library") -> RedirectResponse:
    """Create a redirect response with session cookie set."""
    token = create_access_token(data={"sub": user.email, "user_id": user.id})
    session_expire_hours = get_session_expiration_hours()

    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=session_expire_hours * 3600,
        samesite="lax",
    )
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    current_user: User = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Display registration page (only available if no users exist)."""
    from ..utils.flash import get_flashed_messages

    user_count = db.query(User).count()

    if current_user:
        return RedirectResponse(url="/library", status_code=status.HTTP_303_SEE_OTHER)

    if user_count > 0:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={
            "messages": get_flashed_messages(request),
        },
    )


@router.post("/register")
@limiter.limit("5/hour")
async def register(
    request: Request,
    response: Response,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    """Process registration form (creates first admin user, logs them in directly)."""
    from ..utils.flash import flash

    user_count = db.query(User).count()

    if user_count > 0:
        flash(request, "Registration is not available. Please request an invite from an admin.", "error")
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Create first user as admin (no password needed)
    user = create_user(db, email, role="admin")
    update_last_login(db, user)

    return _create_session_response(user)


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: str = Query(None),
    current_user: User = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Display login page."""
    from ..utils.flash import get_flashed_messages

    user_count = db.query(User).count()
    if user_count == 0:
        return RedirectResponse(url="/auth/register", status_code=status.HTTP_303_SEE_OTHER)

    if current_user:
        return RedirectResponse(url="/library", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "next": next,
            "messages": get_flashed_messages(request),
        },
    )


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    next: str = Form(None),
    db: Session = Depends(get_db),
):
    """Process login form - generate magic link and send email."""
    from ..utils.flash import flash

    # Check if user exists (but always show success to prevent enumeration)
    user = db.query(User).filter(User.email == email).first()

    if user:
        # Generate magic link
        token = create_magic_link(db, email)

        # Send email
        email_service = EmailService()
        email_sent = await email_service.send_magic_link_email(
            recipient_email=email,
            magic_link_token=token,
        )

        # If email not sent (SMTP not configured), log the URL
        if not email_sent:
            domain = SettingsService.get_domain(db)
            magic_url = f"{domain}/auth/magic-link?token={token}"
            print(f"\n{'='*60}")
            print(f"MAGIC LINK (SMTP not configured)")
            print(f"Email: {email}")
            print(f"Login URL: {magic_url}")
            print(f"{'='*60}\n")

    # Always show the same message (prevents email enumeration)
    return templates.TemplateResponse(
        request=request,
        name="auth/magic_link_sent.html",
        context={
            "email": email,
        },
    )


@router.get("/magic-link", response_class=HTMLResponse)
async def magic_link_verify(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Validate magic link token and create session."""
    user = verify_magic_link(db, token)

    if not user:
        return templates.TemplateResponse(
            request=request,
            name="auth/magic_link_expired.html",
            context={},
        )

    # Update last login
    update_last_login(db, user)

    return _create_session_response(user)


@router.get("/logout")
async def logout(response: Response):
    """Log out the current user."""
    redirect_response = RedirectResponse(
        url="/auth/login", status_code=status.HTTP_303_SEE_OTHER
    )
    redirect_response.delete_cookie(key="session_token")
    return redirect_response


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Display user profile page."""
    from ..utils.flash import get_flashed_messages

    return templates.TemplateResponse(
        request=request,
        name="auth/profile.html",
        context={
            "current_user": current_user,
            "messages": get_flashed_messages(request),
        },
    )
