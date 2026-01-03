"""Authentication routes - login, logout, accept invite."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..auth import (
    authenticate_user,
    create_access_token,
    create_user,
    get_password_hash,
    update_last_login,
)
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user, get_optional_user
from ..models import Invite, PasswordReset, User
from ..services.email_service import EmailService
from ..services.settings_service import SettingsService
from ..utils.tokens import generate_reset_token

router = APIRouter(prefix="/auth", tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")

# Rate limiter for authentication endpoints
limiter = Limiter(key_func=get_remote_address)


def get_session_expiration_hours() -> int:
    """
    Get session expiration time in hours from settings with caching.

    Returns:
        Session expiration time in hours (default: 168 hours = 7 days)
    """
    from ..utils.settings_cache import get_cached_setting
    return get_cached_setting("session_expire_hours", 168, int)


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    current_user: User = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Display registration page (only available if no users exist)."""
    from ..utils.flash import get_flashed_messages

    # Check if any users exist
    user_count = db.query(User).count()

    # Redirect if already logged in
    if current_user:
        return RedirectResponse(url="/library", status_code=status.HTTP_303_SEE_OTHER)

    # If users exist, registration is not allowed (must use invites)
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
@limiter.limit("5/hour")  # Allow 5 registration attempts per hour
async def register(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    """Process registration form (creates first admin user)."""
    from ..utils.flash import flash

    # Check if any users exist
    user_count = db.query(User).count()

    # If users exist, registration is not allowed
    if user_count > 0:
        flash(request, "Registration is not available. Please request an invite from an admin.", "error")
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Validate passwords match
    if password != password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )

    # Create first user as admin
    user = create_user(db, email, password, role="admin")

    # Create session token
    token = create_access_token(data={"sub": user.email, "user_id": user.id})

    # Set HTTP-only cookie with configured expiration
    session_expire_hours = get_session_expiration_hours()

    redirect_response = RedirectResponse(
        url="/library", status_code=status.HTTP_303_SEE_OTHER
    )
    redirect_response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=session_expire_hours * 3600,
        samesite="lax",
    )

    return redirect_response


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: str = Query(None),
    current_user: User = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Display login page."""
    from ..utils.flash import get_flashed_messages

    # Check if any users exist
    user_count = db.query(User).count()
    if user_count == 0:
        # No users - redirect to registration
        return RedirectResponse(url="/auth/register", status_code=status.HTTP_303_SEE_OTHER)

    # Redirect if already logged in
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
@limiter.limit("10/minute")  # Allow 10 login attempts per minute
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None),
    db: Session = Depends(get_db),
):
    """Process login form."""
    user = authenticate_user(db, email, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Update last login
    update_last_login(db, user)

    # Create session token
    token = create_access_token(data={"sub": user.email, "user_id": user.id})

    # Get session expiration from database settings (with hardcoded default)
    session_expire_hours = 168  # Default: 7 days
    try:
        from ..services.settings_service import SettingsService
        settings_service = SettingsService(db)
        db_expire = settings_service.get("session_expire_hours")
        if db_expire:
            session_expire_hours = int(db_expire)
    except Exception:
        pass  # Use hardcoded default

    # Set HTTP-only cookie
    redirect_url = next if next else "/library"
    redirect_response = RedirectResponse(
        url=redirect_url, status_code=status.HTTP_303_SEE_OTHER
    )
    redirect_response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=session_expire_hours * 3600,
        samesite="lax",
    )

    return redirect_response


@router.get("/logout")
async def logout(response: Response):
    """Log out the current user."""
    redirect_response = RedirectResponse(
        url="/auth/login", status_code=status.HTTP_303_SEE_OTHER
    )
    redirect_response.delete_cookie(key="session_token")
    return redirect_response


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(
    request: Request,
):
    """Display forgot password form."""
    from ..utils.flash import get_flashed_messages

    return templates.TemplateResponse(
        "auth/forgot_password.html",
        {
            "request": request,
            "messages": get_flashed_messages(request),
        },
    )


@router.post("/forgot-password")
@limiter.limit("5/hour")  # Limit forgot password requests to prevent abuse
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    """Process forgot password request."""
    from ..utils.flash import flash

    # Always show success message to prevent email enumeration attacks
    success_message = "If an account with that email exists, we've sent a password reset link."

    # Check if user exists
    user = db.query(User).filter(User.email == email).first()

    if user:
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

    # Always show the same message (prevents email enumeration)
    flash(request, success_message, "success")
    return RedirectResponse(
        url="/auth/forgot-password",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/accept-invite", response_class=HTMLResponse)
async def accept_invite_page(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Display invite acceptance page."""
    # Find invite by token
    invite = db.query(Invite).filter(Invite.token == token).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invite token",
        )

    if invite.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite has already been used",
        )

    if invite.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite has expired",
        )

    return templates.TemplateResponse(
        request=request,
        name="auth/accept_invite.html",
        context={
            "invite": invite,
            "token": token,
        },
    )


@router.post("/accept-invite")
async def accept_invite(
    response: Response,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    """Process invite acceptance and create user account."""
    # Validate passwords match
    if password != password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )

    # Find invite by token
    invite = db.query(Invite).filter(Invite.token == token).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invite token",
        )

    if invite.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite has already been used",
        )

    if invite.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite has expired",
        )

    # Create user
    user = create_user(db, invite.email, password, role=invite.role.value)

    # Mark invite as used
    invite.used = True
    db.commit()

    # Create session token
    token = create_access_token(data={"sub": user.email, "user_id": user.id})

    # Set HTTP-only cookie with configured expiration
    session_expire_hours = get_session_expiration_hours()

    redirect_response = RedirectResponse(
        url="/library", status_code=status.HTTP_303_SEE_OTHER
    )
    redirect_response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=session_expire_hours * 3600,
        samesite="lax",
    )

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


@router.post("/change-password")
@limiter.limit("5/hour")  # Allow 5 password change attempts per hour
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change user password."""
    from ..auth import verify_password
    from ..utils.flash import flash

    # Verify passwords match
    if new_password != new_password_confirm:
        flash(request, "New passwords do not match", "error")
        return RedirectResponse(
            url="/auth/profile",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Verify current password
    if not verify_password(current_password, current_user.password_hash):
        flash(request, "Current password is incorrect", "error")
        return RedirectResponse(
            url="/auth/profile",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Update password
    current_user.password_hash = get_password_hash(new_password)
    db.commit()

    flash(request, "Password changed successfully!", "success")
    return RedirectResponse(
        url="/auth/profile",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Display password reset form."""
    from ..models import PasswordReset
    from ..utils.flash import flash, get_flashed_messages

    # Validate token
    reset_request = (
        db.query(PasswordReset)
        .filter(PasswordReset.token == token, PasswordReset.used == False)
        .first()
    )

    if not reset_request:
        flash(request, "Invalid or expired reset link. Please request a new password reset link from your administrator.", "error")
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Check if expired
    if reset_request.expires_at < datetime.utcnow():
        flash(request, "This reset link has expired. Please request a new password reset link from your administrator.", "error")
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        request=request,
        name="auth/reset_password.html",
        context={
            "token": token,
            "messages": get_flashed_messages(request),
        },
    )


@router.post("/reset-password")
@limiter.limit("5/hour")  # Allow 5 password reset attempts per hour
async def reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    """Process password reset."""
    from ..models import PasswordReset
    from ..utils.flash import flash

    # Validate passwords match
    if password != password_confirm:
        flash(request, "Passwords do not match", "error")
        return RedirectResponse(
            url=f"/auth/reset-password?token={token}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Validate token
    reset_request = (
        db.query(PasswordReset)
        .filter(PasswordReset.token == token, PasswordReset.used == False)
        .first()
    )

    if not reset_request:
        flash(request, "Invalid or expired reset link", "error")
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Check if expired
    if reset_request.expires_at < datetime.utcnow():
        flash(request, "This reset link has expired", "error")
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Get user
    from ..models import User

    user = db.query(User).filter(User.id == reset_request.user_id).first()

    if not user:
        flash(request, "User not found", "error")
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Update password
    user.password_hash = get_password_hash(password)

    # Mark token as used
    reset_request.used = True

    db.commit()

    # Redirect to login with success message
    flash(request, "Password reset successfully! You can now log in with your new password.", "success")
    return RedirectResponse(
        url="/auth/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )
