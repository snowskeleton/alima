"""Main FastAPI application entry point."""

import json
import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import Depends, FastAPI, Request, status
from sqlalchemy.orm import Session

# Ensure logs directory exists
logs_dir = Path("/app/data/logs") if Path("/app").exists() else Path("data/logs")
logs_dir.mkdir(parents=True, exist_ok=True)

# Import email notification handler
from app.services.email_logging_handler import EmailNotificationHandler

# Configure logging with both file and console handlers
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        # Console handler (for docker logs and local dev)
        logging.StreamHandler(),
        # Combined log file (all levels INFO and above)
        RotatingFileHandler(
            logs_dir / "alima.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        ),
        # Error log file (errors and critical only)
        RotatingFileHandler(
            logs_dir / "alima-error.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        ),
        # Email notification handler (WARNING and above)
        EmailNotificationHandler(level=logging.WARNING),
    ],
)

# Configure error handler to only log WARNING and above
error_handler = logging.getLogger().handlers[2]  # Third handler is error log
error_handler.setLevel(logging.WARNING)

# Silence noisy loggers
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.ERROR)
logging.getLogger("apscheduler.executors.default").setLevel(logging.ERROR)
logging.getLogger("audible.auth").setLevel(logging.WARNING)


def format_dict_pretty(data: dict) -> str:
    """Format a dictionary as pretty-printed JSON for logging."""
    return "\n" + json.dumps(data, indent=2, default=str)

logger = logging.getLogger(__name__)

from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import settings
from .database import get_db, init_db

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)


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


class NoIndexMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add X-Robots-Tag header to all responses.

    This prevents search engines from indexing any page on the site.
    """
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet, noimageindex"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager with leader election.

    Only the leader worker runs migrations, starts scheduler, etc.
    """
    # Skip initialization in test mode (tests manage their own database)
    if settings.environment != "testing":
        # Import leader election module
        from .leader_election import LeaderElection

        # Try to acquire leadership
        is_leader = LeaderElection.try_acquire_leadership()

        if is_leader:
            # === LEADER TASKS ===
            logger.info(f"Worker {os.getpid()} is LEADER - running startup tasks")

            # Initialize database
            init_db()
            print("✓ Database initialized")

            # Run pending migrations (LEADER ONLY)
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

            # Reclaim downloads the previous process died holding, before the
            # scheduler starts handing out work (LEADER ONLY)
            from .workers.scheduler import (
                recover_interrupted_downloads,
                start_scheduler,
                stop_scheduler,
            )

            recover_interrupted_downloads()
            print("✓ Interrupted downloads recovered")

            # Start background scheduler (LEADER ONLY)
            start_scheduler()
            print("✓ Background scheduler started")

        else:
            # === FOLLOWER TASKS ===
            logger.info(f"Worker {os.getpid()} is FOLLOWER - skipping startup tasks")

            # Wait briefly for leader to initialize database
            import time
            time.sleep(2)

            # Ensure data directories exist (safe for all workers)
            settings.audiobooks_path.mkdir(parents=True, exist_ok=True)
            settings.covers_path.mkdir(parents=True, exist_ok=True)
            settings.audible_auth_path.mkdir(parents=True, exist_ok=True)
            settings.temp_path.mkdir(parents=True, exist_ok=True)

    yield

    # === SHUTDOWN ===
    if settings.environment != "testing":
        from .leader_election import LeaderElection

        if LeaderElection.is_leader():
            # Stop scheduler (LEADER ONLY)
            from .workers.scheduler import stop_scheduler
            stop_scheduler()
            logger.info(f"Worker {os.getpid()} (LEADER) shutting down")

            # Release lock
            LeaderElection.release_leadership()
        else:
            logger.info(f"Worker {os.getpid()} (FOLLOWER) shutting down")

    print("Shutting down...")


API_DESCRIPTION = """\
Audible Library Manager - download and manage audiobooks with RSS feeds.

## Authentication

Every authenticated endpoint accepts **either** of:

* `Authorization: Bearer <api-key>` - programmatic access. Create a key in the
  web UI under Settings -> API keys; the full key is shown only once, at
  creation. Key management endpoints accept browser sessions only, so a key
  can never mint or revoke keys.
* `session_token` cookie - the JWT issued to browsers after a magic-link login.

API keys inherit the role of the user that owns them, so admin-only endpoints
require a key belonging to an admin.

Unauthenticated requests to `/api/**` (or any request sending `Authorization`
or `Accept: application/json`) get `401` with a JSON body; browser page requests
are redirected to the login page instead.

## Machine-readable schema

* `GET /openapi.json` - the full OpenAPI 3.1 document for this server
* `GET /docs` - Swagger UI
* `GET /redoc` - ReDoc

## API surface

* `/api/v2/**` - the primary API, used by the web frontend and available to
  API-key clients.
* `/api/v1/**` - a small legacy external API; API-key only.
"""

OPENAPI_TAGS = [
    {"name": "Health", "description": "Liveness and build information."},
    {"name": "Root", "description": "Entry points and static resources."},
    {"name": "API", "description": "Legacy /api/v1 external API (API key only)."},
    {"name": "API v2", "description": "Primary /api/v2 API: books, feeds, downloads, jobs, users, settings."},
    {"name": "SPA", "description": "Catch-all serving the React single-page app."},
]

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description=API_DESCRIPTION,
    summary="Audiobook library management API",
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Exception handler for authentication redirects
from .dependencies import UnauthenticatedException


@app.exception_handler(UnauthenticatedException)
async def unauthenticated_exception_handler(request: Request, exc: UnauthenticatedException):
    """Handle authentication exceptions by redirecting to login/register."""
    return RedirectResponse(url=exc.redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# Force HTTPS URLs when DOMAIN is set to HTTPS
# This ensures correct URL generation behind reverse proxies
app.add_middleware(HTTPSRedirectMiddleware)

# Add X-Robots-Tag header to prevent search engine indexing
app.add_middleware(NoIndexMiddleware)

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


@app.get("/robots.txt", response_class=PlainTextResponse, tags=["Root"])
async def robots():
    """
    Serve robots.txt to block search engines and AI crawlers.

    Returns robots.txt file that disallows all crawlers from indexing the site.
    """
    from pathlib import Path
    robots_path = Path("app/static/robots.txt")
    return robots_path.read_text()


@app.get("/api", tags=["Root"])
async def api_index(request: Request):
    """
    API discovery index.

    Small, unauthenticated entry point so a client (or another tool) can find
    the schema and learn how to authenticate without scraping the UI.
    """
    base = str(request.base_url).rstrip("/")
    return JSONResponse(
        content={
            "name": settings.app_name,
            "version": "2.0.0",
            "openapi": f"{base}/openapi.json",
            "docs": {"swagger": f"{base}/docs", "redoc": f"{base}/redoc"},
            "versions": {
                "v2": f"{base}/api/v2",
                "v1": f"{base}/api/v1",
            },
            "authentication": {
                "scheme": "bearer",
                "header": "Authorization: Bearer <api-key>",
                "create_key": (
                    "Web UI only: Settings -> API keys. Key management requires "
                    "a logged-in browser session and cannot be done with a key."
                ),
                "note": (
                    "API keys carry the role of the user that created them. "
                    "Browser sessions may instead use the session_token cookie."
                ),
            },
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


# Include routers — functional endpoints only (files, RSS, external API)
from .routers import ext_api, files, rss
from .routers.api_v2 import router as api_v2_router

app.include_router(rss.router, prefix="/feed")
app.include_router(rss.router, prefix="/feeds")
app.include_router(files.router)
app.include_router(ext_api.router)
app.include_router(api_v2_router)

# SPA catch-all: serve React frontend for all unmatched routes
_spa_dir = Path("app/static/spa")
_spa_assets_dir = _spa_dir / "assets"
_spa_assets_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(_spa_assets_dir)), name="spa-assets")


@app.get("/{full_path:path}", tags=["SPA"])
async def spa_catch_all(request: Request, full_path: str):
    """Serve React SPA for all unmatched routes."""
    from starlette.responses import FileResponse

    spa_index = _spa_dir / "index.html"
    if spa_index.exists():
        return FileResponse(str(spa_index))
    return JSONResponse(
        status_code=503,
        content={"error": "Frontend not built. Run: cd frontend && npm run build"},
    )
