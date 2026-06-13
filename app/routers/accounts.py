"""Admin routes for Audible account management."""

import secrets
from pathlib import Path
from typing import Dict

from audible import Authenticator
from audible.localization import Locale
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import require_admin
from ..models import AudibleAccount, User
from ..schemas import AudibleAccountCreate, AudibleAccountResponse

router = APIRouter(prefix="/admin/accounts", tags=["Admin - Accounts"])
templates = Jinja2Templates(directory="app/templates")

# Temporary storage for login sessions (in production, use Redis or similar)
login_sessions: Dict[str, dict] = {}


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    current_user: User = Depends(require_admin),
):
    """Show the external browser login page."""
    # Available marketplaces
    marketplaces = {
        "us": "United States",
        "uk": "United Kingdom",
        "de": "Germany",
        "fr": "France",
        "ca": "Canada",
        "au": "Australia",
        "in": "India",
        "it": "Italy",
        "jp": "Japan",
        "es": "Spain",
    }

    return templates.TemplateResponse(
        request=request,
        name="admin/accounts_login.html",
        context={
            "current_user": current_user,
            "marketplaces": marketplaces,
        },
    )


@router.post("/login/generate-url")
async def generate_login_url(
    marketplace: str = Form(...),
    with_username: bool = Form(False),
    current_user: User = Depends(require_admin),
):
    """Generate OAuth login URL for external browser authentication."""
    # Create session ID
    session_id = secrets.token_urlsafe(32)

    # Build OAuth URL using audible library's helper
    from audible.login import build_oauth_url, create_code_verifier

    locale = Locale(marketplace)
    code_verifier = create_code_verifier()

    oauth_url, serial = build_oauth_url(
        country_code=locale.country_code,
        domain=locale.domain,
        market_place_id=locale.market_place_id,
        code_verifier=code_verifier,
        with_username=with_username,
    )

    # Store session data
    login_sessions[session_id] = {
        "code_verifier": code_verifier,
        "serial": serial,
        "marketplace": marketplace,
        "with_username": with_username,
        "domain": locale.domain,
    }

    return JSONResponse({
        "session_id": session_id,
        "oauth_url": oauth_url,
    })


@router.post("/login/complete")
async def complete_login(
    session_id: str = Form(...),
    redirect_url: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Complete authentication using redirect URL from external browser."""
    # Get session data
    session_data = login_sessions.get(session_id)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired session. Please start over.",
        )

    try:
        # Extract authorization code from redirect URL
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(redirect_url)
        query_params = parse_qs(parsed.query)

        if "openid.oa2.authorization_code" not in query_params:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid redirect URL. Make sure you copied the complete URL from your browser.",
            )

        authorization_code = query_params["openid.oa2.authorization_code"][0]

        # Register device and get auth credentials
        from audible.register import register

        register_data = register(
            authorization_code=authorization_code,
            code_verifier=session_data["code_verifier"],
            domain=session_data["domain"],
            serial=session_data["serial"],
            with_username=session_data["with_username"],
        )

        # Create Authenticator and save to file
        auth = Authenticator()
        auth.locale = Locale(session_data["marketplace"])
        auth._update_attrs(
            with_username=session_data["with_username"],
            **register_data
        )

        # Get activation bytes
        activation_bytes = auth.get_activation_bytes()

        # Get user info to determine username
        user_info = auth.user_profile()
        username = user_info.get("name") or user_info.get("email") or session_data["serial"]

        # Check if account already exists
        existing = db.query(AudibleAccount).filter(
            AudibleAccount.username == username
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Account '{username}' already exists. Please delete the existing account first.",
            )

        # Ensure auth directory exists
        settings.audible_auth_path.mkdir(parents=True, exist_ok=True)

        # Save auth file
        auth_filename = f"{username}.json"
        auth_file_path = settings.audible_auth_path / auth_filename
        auth.to_file(filename=auth_file_path, encryption=False)

        # Create account record
        account = AudibleAccount(
            username=username,
            auth_file_path=auth_filename,
            activation_bytes=activation_bytes,
            marketplace=session_data["marketplace"],
            enabled=True,
        )
        db.add(account)
        db.commit()

        # Clean up session
        del login_sessions[session_id]

        return JSONResponse({
            "success": True,
            "username": username,
            "message": f"Successfully added Audible account '{username}'",
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}",
        )


@router.get("", response_class=HTMLResponse)
async def list_accounts(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all Audible accounts."""
    accounts = db.query(AudibleAccount).order_by(AudibleAccount.added_at.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="admin/accounts.html",
        context={
            "current_user": current_user,
            "accounts": accounts,
        },
    )


@router.post("/add", response_class=HTMLResponse)
async def add_account(
    username: str = Form(...),
    auth_file: UploadFile = File(...),
    marketplace: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Add a new Audible account via web form."""
    import json

    # Check if account already exists
    existing = (
        db.query(AudibleAccount)
        .filter(AudibleAccount.username == username)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account with username '{username}' already exists",
        )

    # Read the uploaded file content
    content = await auth_file.read()

    # Parse JSON to extract activation_bytes
    try:
        auth_data = json.loads(content)
        activation_bytes = auth_data.get("activation_bytes")

        if not activation_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Auth file does not contain activation_bytes. Please ensure this is a valid Audible auth file.",
            )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON file. Please upload a valid Audible auth file.",
        )

    # Ensure auth directory exists
    settings.audible_auth_path.mkdir(parents=True, exist_ok=True)

    # Save uploaded auth file
    auth_filename = f"{username}.json"
    auth_file_path = settings.audible_auth_path / auth_filename

    with open(auth_file_path, "wb") as f:
        f.write(content)

    # Create new account
    account = AudibleAccount(
        username=username,
        auth_file_path=auth_filename,
        activation_bytes=activation_bytes,
        marketplace=marketplace,
        enabled=True,
    )
    db.add(account)
    db.commit()

    # Redirect back to accounts page
    return RedirectResponse(url="/admin/accounts", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{account_id}/toggle", response_class=HTMLResponse)
async def toggle_account(
    account_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Enable or disable an Audible account."""
    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account with ID {account_id} not found",
        )

    account.enabled = not account.enabled
    db.commit()

    return RedirectResponse(url="/admin/accounts", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{account_id}/toggle-downloads", response_class=HTMLResponse)
async def toggle_downloads(
    account_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Enable or disable downloads for an Audible account."""
    from ..models import DownloadQueue, DownloadStatus

    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account with ID {account_id} not found",
        )

    account.downloads_enabled = not account.downloads_enabled

    # If disabling downloads, clear all pending queue entries for this account
    if not account.downloads_enabled:
        pending_entries = db.query(DownloadQueue).filter(
            DownloadQueue.audible_account_id == account_id,
            DownloadQueue.status.in_([
                DownloadStatus.PENDING,
                DownloadStatus.DOWNLOADING,
                DownloadStatus.DECRYPTING
            ])
        ).all()

        for entry in pending_entries:
            db.delete(entry)

    db.commit()

    return RedirectResponse(url="/admin/accounts", status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete an Audible account."""
    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account with ID {account_id} not found",
        )

    # TODO: Consider what to do with books associated with this account
    # For now, we'll keep the books but set audible_account_id to NULL

    db.delete(account)
    db.commit()

    return {"message": f"Account '{account.username}' deleted successfully"}


@router.post("/{account_id}/sync", response_class=HTMLResponse)
async def trigger_sync(
    request: Request,
    account_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Manually trigger a library sync for this account in the background."""
    from ..services.audible_sync import AudibleSyncService
    from ..services.background_jobs import BackgroundJobService

    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account with ID {account_id} not found",
        )

    if not account.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account '{account.username}' is disabled",
        )

    def _sync_job(job_db, job):
        sync_service = AudibleSyncService(job_db)
        acct = job_db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
        stats = sync_service.sync_account(acct)
        return stats

    job = BackgroundJobService.create_job(db, "sync", meta={"account_id": account_id})
    BackgroundJobService.submit(job.id, _sync_job)

    return RedirectResponse(url="/admin/accounts", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{account_id}/queue-all", response_class=HTMLResponse)
async def queue_all_books(
    account_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Queue all undownloaded books from this account for download."""
    from ..models import Book, DownloadQueue, DownloadStatus, DownloadType

    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account with ID {account_id} not found",
        )

    # Get all books for this account that don't have files
    books_without_files = db.query(Book).filter(
        Book.audible_account_id == account_id,
        Book.file_path.is_(None)
    ).all()

    stats = {
        "queued": 0,
        "requeued": 0,
        "already_queued": 0,
        "skipped": 0,
    }

    for book in books_without_files:
        # Check if book has download enabled
        if not book.download_enabled:
            stats["skipped"] += 1
            continue

        # Check if there's an existing queue entry for this book
        existing_entry = db.query(DownloadQueue).filter(
            DownloadQueue.book_id == book.id,
            DownloadQueue.download_type == DownloadType.BOOK
        ).first()

        if existing_entry:
            # If it's pending or downloading, skip
            if existing_entry.status in [DownloadStatus.PENDING, DownloadStatus.DOWNLOADING, DownloadStatus.DECRYPTING]:
                stats["already_queued"] += 1
                continue

            # If it's failed or completed, reset to pending
            if existing_entry.status in [DownloadStatus.FAILED, DownloadStatus.COMPLETED]:
                existing_entry.status = DownloadStatus.PENDING
                existing_entry.attempts = 0
                existing_entry.error_message = None
                stats["requeued"] += 1
        else:
            # Create new queue entry
            queue_entry = DownloadQueue(
                book_id=book.id,
                audible_account_id=account_id,
                asin=book.asin,
                download_type=DownloadType.BOOK,
                priority=0,
                status=DownloadStatus.PENDING,
                attempts=0,
            )
            db.add(queue_entry)
            stats["queued"] += 1

    db.commit()

    return RedirectResponse(url="/admin/accounts", status_code=status.HTTP_303_SEE_OTHER)
