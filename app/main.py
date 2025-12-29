"""Main FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Silence noisy loggers
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import settings
from .database import get_db, init_db


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    Middleware to force HTTPS URLs in responses.

    When behind a reverse proxy (Caddy), this ensures all generated URLs use HTTPS.
    """
    async def dispatch(self, request, call_next):
        # Check if we're behind a proxy with HTTPS
        forwarded_proto = request.headers.get("x-forwarded-proto", "")

        # Check domain from database settings (with config fallback)
        try:
            from .database import SessionLocal
            from .services.settings_service import SettingsService
            db = SessionLocal()
            domain = SettingsService.get_domain(db)
            db.close()
        except Exception:
            # Fallback to config if database not available
            domain = settings.domain

        # If domain is HTTPS, force HTTPS for all URLs
        if domain.startswith("https://"):
            request.scope["scheme"] = "https"
        elif forwarded_proto == "https":
            request.scope["scheme"] = "https"

        response = await call_next(request)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Skip initialization in test mode (tests manage their own database)
    if settings.environment != "testing":
        # Startup: Initialize database
        init_db()
        print("✓ Database initialized")

        # Run pending migrations
        from .database import SessionLocal
        from .migrations_runner import run_all_pending_migrations

        db = SessionLocal()
        try:
            run_all_pending_migrations(db)
            print("✓ Database migrations applied")
        except Exception as e:
            print(f"⚠ Warning: Migration error (continuing anyway): {e}")
        finally:
            db.close()

        # Ensure data directories exist
        settings.audiobooks_path.mkdir(parents=True, exist_ok=True)
        settings.covers_path.mkdir(parents=True, exist_ok=True)
        settings.audible_auth_path.mkdir(parents=True, exist_ok=True)
        settings.temp_path.mkdir(parents=True, exist_ok=True)
        print("✓ Data directories created")

        # Start background scheduler
        from .workers.scheduler import start_scheduler, stop_scheduler

        start_scheduler()
        print("✓ Background scheduler started")

    yield

    # Shutdown: Stop scheduler
    if settings.environment != "testing":
        stop_scheduler()
    print("Shutting down...")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Audible Library Manager - Download and manage audiobooks with RSS feeds",
    version="2.0.0",
    lifespan=lifespan,
)


# Exception handler for authentication redirects
from .dependencies import UnauthenticatedException

templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(UnauthenticatedException)
async def unauthenticated_exception_handler(request: Request, exc: UnauthenticatedException):
    """Handle authentication exceptions by redirecting to login/register."""
    return RedirectResponse(url=exc.redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with user-friendly HTML error page."""
    from .utils.flash import flash

    # Extract error details
    errors = exc.errors()
    error_messages = []
    for error in errors:
        field = " → ".join(str(loc) for loc in error["loc"])
        msg = error["msg"]
        error_messages.append(f"{field}: {msg}")

    error_text = "; ".join(error_messages)

    # Flash error and redirect back
    flash(request, f"Validation error: {error_text}", "error")

    # Try to redirect to referer, or a sensible default
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)


# Add session middleware for flash messages
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="alima_session",
    max_age=7 * 24 * 60 * 60,  # 7 days
    same_site="lax",
    https_only=settings.domain.startswith("https://"),
)

# Force HTTPS URLs when DOMAIN is set to HTTPS
# This ensures correct URL generation behind reverse proxies
app.add_middleware(HTTPSRedirectMiddleware)

# Trust proxy headers (for HTTPS behind reverse proxy)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"],  # Or specify your domain: ["alima.snowskeleton.net"]
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.

    Returns application status and configuration info.
    """
    return JSONResponse(
        content={
            "status": "healthy",
            "app_name": settings.app_name,
            "version": "2.0.0",
            "environment": settings.environment,
            "replication_mode": settings.replication_mode,
        }
    )


@app.get("/", tags=["Root"])
async def root(db: Session = Depends(get_db)):
    """
    Root endpoint.

    Redirects to appropriate page based on system state.
    """
    from .models import User

    # Check if any users exist
    user_count = db.query(User).count()
    if user_count == 0:
        # No users - redirect to registration
        return RedirectResponse(url="/auth/register", status_code=303)

    # Users exist - redirect to login/library
    return RedirectResponse(url="/library", status_code=303)


# Include routers
from .routers import accounts, admin, api, auth, books, downloads, feeds, files, import_books, library, match_books, rss
from .routers import settings as settings_router

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(admin.router)
app.include_router(api.router)
app.include_router(downloads.router)
app.include_router(library.router)
app.include_router(books.router)
app.include_router(feeds.router)
app.include_router(feeds.feed_detail_router)
app.include_router(import_books.router)
app.include_router(match_books.router)
app.include_router(rss.router)
app.include_router(files.router)
app.include_router(settings_router.router)
