"""API v2 routers for the React SPA frontend."""

from fastapi import APIRouter

from . import auth, books, jobs, feeds, accounts, downloads, users, admin, settings as settings_router, logs, audit, match_books, import_books

router = APIRouter(prefix="/api/v2", tags=["API v2"])

router.include_router(auth.router)
router.include_router(books.router)
router.include_router(jobs.router)
router.include_router(feeds.router)
router.include_router(accounts.router)
router.include_router(downloads.router)
router.include_router(users.router)
router.include_router(admin.router)
router.include_router(settings_router.router)
router.include_router(logs.router)
router.include_router(audit.router)
router.include_router(match_books.router)
router.include_router(import_books.router)
