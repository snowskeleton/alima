"""API v2 authentication routes."""

import logging

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ...auth import (
    create_access_token,
    create_magic_link,
    create_user,
    update_last_login,
    verify_magic_link,
)
from ...database import get_db
from ...dependencies import get_current_user
from ...models import User, UserRole
from ...services.email_service import EmailService
from ...services.settings_service import SettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])
limiter = Limiter(key_func=get_remote_address)


def _get_session_expiration_hours() -> int:
    from ...utils.settings_cache import get_cached_setting
    return get_cached_setting("session_expire_hours", 168, int)


def _set_session_cookie(response: Response, user: User):
    """Set session cookie on a response."""
    token = create_access_token(data={"sub": user.email, "user_id": user.id})
    session_expire_hours = _get_session_expiration_hours()
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=session_expire_hours * 3600,
        samesite="lax",
    )


class LoginRequest(BaseModel):
    email: EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr


@router.get("/status")
async def auth_status(
    session_token: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """Check authentication status. Returns user info if authenticated."""
    user_count = db.query(User).count()

    if user_count == 0:
        return {"authenticated": False, "user": None, "needs_registration": True}

    if not session_token:
        return {"authenticated": False, "user": None, "needs_registration": False}

    from ...auth import verify_token
    token_data = verify_token(session_token)
    if not token_data or not token_data.email:
        return {"authenticated": False, "user": None, "needs_registration": False}

    user = db.query(User).filter(User.email == token_data.email).first()
    if not user:
        return {"authenticated": False, "user": None, "needs_registration": False}

    return {
        "authenticated": True,
        "needs_registration": False,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role.value,
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
        },
    }


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
):
    """Send magic link to email. Always returns success to prevent enumeration."""
    user = db.query(User).filter(User.email == body.email).first()

    if user:
        token = create_magic_link(db, body.email)
        email_service = EmailService()
        email_sent = await email_service.send_magic_link_email(
            recipient_email=body.email,
            magic_link_token=token,
        )

        if not email_sent:
            domain = SettingsService.get_domain(db)
            magic_url = f"{domain}/auth/magic-link?token={token}"
            print(f"\n{'='*60}")
            print(f"MAGIC LINK (SMTP not configured)")
            print(f"Email: {body.email}")
            print(f"Login URL: {magic_url}")
            print(f"{'='*60}\n")

    return {"sent": True}


@router.get("/magic-link")
async def verify_magic_link_endpoint(
    token: str,
    response: Response,
    db: Session = Depends(get_db),
):
    """Validate magic link token and set session cookie."""
    user = verify_magic_link(db, token)

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "Invalid or expired magic link"},
        )

    update_last_login(db, user)

    resp = JSONResponse(content={
        "success": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role.value,
        },
    })
    _set_session_cookie(resp, user)
    return resp


@router.post("/register")
@limiter.limit("5/hour")
async def register(
    request: Request,
    body: RegisterRequest,
    db: Session = Depends(get_db),
):
    """Create first admin user. Only works when no users exist."""
    user_count = db.query(User).count()

    if user_count > 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Registration is not available"},
        )

    user = create_user(db, body.email, role="admin")
    update_last_login(db, user)

    resp = JSONResponse(content={
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role.value,
        },
    })
    _set_session_cookie(resp, user)
    return resp


@router.post("/logout")
async def logout():
    """Clear session cookie."""
    resp = JSONResponse(content={"success": True})
    resp.delete_cookie(key="session_token")
    return resp


@router.get("/profile")
async def profile(
    current_user: User = Depends(get_current_user),
):
    """Get current user profile."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role.value,
        "created_at": current_user.created_at.isoformat(),
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
    }
