"""FastAPI dependency injection functions."""

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .auth import verify_token
from .database import get_db
from .models import User, UserRole


async def get_current_user(
    session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from session token.

    Args:
        session_token: JWT token from HTTP-only cookie
        db: Database session

    Returns:
        Current User object

    Raises:
        HTTPException: If not authenticated or token invalid
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not session_token:
        raise credentials_exception

    token_data = verify_token(session_token)
    if token_data is None or token_data.email is None:
        raise credentials_exception

    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception

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
