"""FastAPI dependency injection functions."""

from typing import Optional
from urllib.parse import quote

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .auth import verify_token
from .database import get_db
from .models import User, UserRole


class UnauthenticatedException(HTTPException):
    """Custom exception for unauthenticated users that triggers redirect."""

    def __init__(self, redirect_url: str):
        super().__init__(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Authentication required",
            headers={"Location": redirect_url},
        )
        self.redirect_url = redirect_url


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from session token.

    Args:
        request: FastAPI request object
        session_token: JWT token from HTTP-only cookie
        db: Database session

    Returns:
        Current User object

    Raises:
        UnauthenticatedException: Redirects to appropriate page if not authenticated
    """
    # Check if any users exist in the system
    user_count = db.query(User).count()
    if user_count == 0:
        # No users exist - redirect to registration
        raise UnauthenticatedException(redirect_url="/auth/register")

    if not session_token:
        # Not authenticated - redirect to login with next parameter
        next_url = str(request.url.path)
        if request.url.query:
            next_url += f"?{request.url.query}"
        encoded_next = quote(next_url, safe="")
        raise UnauthenticatedException(redirect_url=f"/auth/login?next={encoded_next}")

    token_data = verify_token(session_token)
    if token_data is None or token_data.email is None:
        # Invalid token - redirect to login
        next_url = str(request.url.path)
        if request.url.query:
            next_url += f"?{request.url.query}"
        encoded_next = quote(next_url, safe="")
        raise UnauthenticatedException(redirect_url=f"/auth/login?next={encoded_next}")

    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        # User not found - redirect to login
        next_url = str(request.url.path)
        if request.url.query:
            next_url += f"?{request.url.query}"
        encoded_next = quote(next_url, safe="")
        raise UnauthenticatedException(redirect_url=f"/auth/login?next={encoded_next}")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get the current active user.

    Args:
        current_user: User from get_current_user dependency

    Returns:
        Current User object

    Note:
        Currently just returns the user. Could be extended to check
        if user is active/enabled if we add that field.
    """
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require admin role for the current user.

    Args:
        current_user: User from get_current_user dependency

    Returns:
        Current User object if admin

    Raises:
        HTTPException: If user is not an admin
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


async def get_optional_user(
    session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get the current user if authenticated, None otherwise.

    Useful for pages that show different content for logged-in users
    but are still accessible to anonymous users.

    Args:
        session_token: JWT token from HTTP-only cookie
        db: Database session

    Returns:
        User object if authenticated, None otherwise
    """
    if not session_token:
        return None

    token_data = verify_token(session_token)
    if token_data is None or token_data.email is None:
        return None

    user = db.query(User).filter(User.email == token_data.email).first()
    return user
