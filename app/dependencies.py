"""FastAPI dependency injection functions."""

import hashlib
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .auth import verify_token
from .database import get_db
from .models import ApiKey, User, UserRole

logger = logging.getLogger(__name__)

# Named so it shows up as a reusable "ApiKeyBearer" security scheme in the
# generated OpenAPI document rather than an anonymous HTTPBearer.
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="ApiKeyBearer",
    description=(
        "API key issued from Settings -> API keys (or POST /api/v2/admin/api-keys). "
        "Send it as `Authorization: Bearer <key>`."
    ),
)


class UnauthenticatedException(HTTPException):
    """Custom exception for unauthenticated users that triggers redirect."""

    def __init__(self, redirect_url: str):
        super().__init__(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Authentication required",
            headers={"Location": redirect_url},
        )
        self.redirect_url = redirect_url


# Stamping last_used_at on every single request would mean a write per API call.
# Only refresh it once the recorded value is this stale, which is accurate enough
# to answer "is this key still in use?" without the write amplification.
LAST_USED_REFRESH_SECONDS = 60


def _user_from_api_key(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: Session,
) -> Optional[User]:
    """
    Resolve a User from an Authorization: Bearer <api key> header.

    Returns None when no credentials were supplied, the key is unknown, or the
    key has expired, so callers can fall back to cookie-based session auth.
    Records the key's last use as a side effect.
    """
    if credentials is None or not credentials.credentials:
        return None

    key_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    if api_key is None:
        return None

    if api_key.is_expired:
        return None

    user = db.query(User).filter(User.id == api_key.user_id).first()
    if user is not None:
        _record_key_use(db, api_key)

    return user


def _record_key_use(db: Session, api_key: ApiKey) -> None:
    """
    Stamp last_used_at, throttled so a busy key isn't written on every request.

    Bookkeeping must never decide the fate of unrelated request state, so if the
    session already has pending changes this skips the stamp rather than
    committing someone else's work (or discarding it on rollback). In practice
    the session is clean here - auth runs during dependency resolution, before
    the endpoint has done anything - and a skipped stamp only costs a little
    precision on a value that is throttled to the minute anyway.

    Never lets a bookkeeping failure break the request that triggered it.
    """
    now = datetime.utcnow()
    if (
        api_key.last_used_at is not None
        and (now - api_key.last_used_at).total_seconds() < LAST_USED_REFRESH_SECONDS
    ):
        return

    if db.new or db.deleted or db.dirty:
        logger.debug("Request session has pending work; skipping API key use stamp")
        return

    try:
        api_key.last_used_at = now
        db.commit()
    except SQLAlchemyError:
        logger.warning("Could not record last use of API key %s", api_key.id, exc_info=True)
        db.rollback()


def _api_key_rejection(credentials: HTTPAuthorizationCredentials, db: Session) -> HTTPException:
    """Explain why a bearer key was refused, distinguishing expired from unknown."""
    key_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()

    detail = "Expired API key" if api_key is not None and api_key.is_expired else "Invalid API key"
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _wants_json(request: Request) -> bool:
    """
    Decide whether an unauthenticated caller should get a 401 instead of a redirect.

    API clients (anything hitting /api/, sending a bearer token, or asking for
    JSON) get a machine-readable 401; browsers keep the login redirect.
    """
    if request.url.path.startswith("/api/"):
        return True
    if request.headers.get("authorization"):
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


def _unauthenticated(request: Request, redirect_url: str) -> HTTPException:
    """Build the right failure for this caller: 401 for APIs, redirect for browsers."""
    if _wants_json(request):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return UnauthenticatedException(redirect_url=redirect_url)


def _login_redirect_url(request: Request) -> str:
    """Login URL that returns the user to the page they asked for."""
    next_url = str(request.url.path)
    if request.url.query:
        next_url += f"?{request.url.query}"
    return f"/auth/login?next={quote(next_url, safe='')}"


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None, include_in_schema=False),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from an API key or session token.

    Authentication is tried in order:
      1. ``Authorization: Bearer <api key>`` header (programmatic access)
      2. ``session_token`` JWT cookie (browser sessions)

    Args:
        request: FastAPI request object
        session_token: JWT token from HTTP-only cookie
        credentials: Bearer credentials holding an API key
        db: Database session

    Returns:
        Current User object

    Raises:
        HTTPException: 401 for API clients
        UnauthenticatedException: Redirects browsers to login/registration
    """
    api_user = _user_from_api_key(credentials, db)
    if api_user is not None:
        return api_user

    # A bearer token was supplied but did not resolve to a user - never fall
    # through to the cookie, and never redirect: the caller is programmatic.
    if credentials is not None:
        raise _api_key_rejection(credentials, db)

    # Check if any users exist in the system
    user_count = db.query(User).count()
    if user_count == 0:
        # No users exist - redirect to registration
        raise _unauthenticated(request, "/auth/register")

    if not session_token:
        raise _unauthenticated(request, _login_redirect_url(request))

    token_data = verify_token(session_token)
    if token_data is None or token_data.email is None:
        raise _unauthenticated(request, _login_redirect_url(request))

    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise _unauthenticated(request, _login_redirect_url(request))

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


async def get_session_user(
    request: Request,
    session_token: Optional[str] = Cookie(None, include_in_schema=False),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the current user from a browser session cookie ONLY.

    Deliberately does not accept an API key. Use this for endpoints that manage
    credentials themselves: if an API key could mint or list API keys, a leaked
    key could issue itself permanent replacements that outlive its revocation.
    Those actions require a fresh human login.

    Args:
        request: FastAPI request object
        session_token: JWT token from HTTP-only cookie
        db: Database session

    Returns:
        Current User object

    Raises:
        HTTPException: 401 for API clients (including any bearer-token caller)
        UnauthenticatedException: Redirects browsers to login
    """
    if not session_token:
        raise _unauthenticated(request, _login_redirect_url(request))

    token_data = verify_token(session_token)
    if token_data is None or token_data.email is None:
        raise _unauthenticated(request, _login_redirect_url(request))

    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise _unauthenticated(request, _login_redirect_url(request))

    return user


async def require_admin_session(
    current_user: User = Depends(get_session_user),
) -> User:
    """
    Require an admin authenticated by browser session, not by API key.

    Args:
        current_user: User from get_session_user dependency

    Returns:
        Current User object if admin

    Raises:
        HTTPException: 403 if user is not an admin
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


async def get_optional_user(
    session_token: Optional[str] = Cookie(None, include_in_schema=False),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Get the current user if authenticated, None otherwise.

    Accepts either an API key bearer token or a session cookie. Useful for
    pages that show different content for logged-in users but are still
    accessible to anonymous users.

    "Optional" means the caller may present no credentials at all - not that a
    credential they did present may be wrong. A bearer token that does not
    resolve is rejected here exactly as it is in get_current_user, rather than
    quietly falling back to whatever cookie the same request happens to carry.

    Args:
        session_token: JWT token from HTTP-only cookie
        credentials: Bearer credentials holding an API key
        db: Database session

    Returns:
        User object if authenticated, None if no credentials were offered

    Raises:
        HTTPException: 401 if a bearer key was offered but is invalid or expired
    """
    api_user = _user_from_api_key(credentials, db)
    if api_user is not None:
        return api_user

    if credentials is not None:
        raise _api_key_rejection(credentials, db)

    if not session_token:
        return None

    token_data = verify_token(session_token)
    if token_data is None or token_data.email is None:
        return None

    return db.query(User).filter(User.email == token_data.email).first()


async def get_api_key_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticate a user via API key from the Authorization: Bearer header.

    Unlike get_current_user this never falls back to a session cookie, so it
    stays appropriate for endpoints that are API-key-only.

    Args:
        credentials: Bearer token credentials
        db: Database session

    Returns:
        The User associated with the API key

    Raises:
        HTTPException: 401 if the key is missing or invalid
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = _user_from_api_key(credentials, db)
    if user is None:
        raise _api_key_rejection(credentials, db)

    return user


async def require_api_admin(
    user: User = Depends(get_api_key_user),
) -> User:
    """
    Require admin role for API key authenticated requests.

    Args:
        user: User from get_api_key_user dependency

    Returns:
        Current User object if admin

    Raises:
        HTTPException: 403 if user is not an admin
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
