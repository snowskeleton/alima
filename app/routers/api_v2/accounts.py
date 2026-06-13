"""API v2 routes for Audible account management."""

import secrets
from typing import Dict

from audible import Authenticator
from audible.localization import Locale
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ...config import settings
from ...database import get_db
from ...dependencies import require_admin
from ...models import AudibleAccount, Book, DownloadQueue, DownloadStatus, DownloadType, User
from ...services.background_jobs import BackgroundJobService

router = APIRouter(prefix="/accounts", tags=["Accounts"])

# Temporary storage for OAuth login sessions
_login_sessions: Dict[str, dict] = {}


def _account_to_dict(account: AudibleAccount) -> dict:
    return {
        "id": account.id,
        "username": account.username,
        "marketplace": account.marketplace,
        "enabled": account.enabled,
        "downloads_enabled": account.downloads_enabled,
        "last_sync_timestamp": account.last_sync_timestamp.isoformat() if account.last_sync_timestamp else None,
        "added_at": account.added_at.isoformat() if account.added_at else None,
    }


@router.get("")
async def list_accounts(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all Audible accounts."""
    accounts = db.query(AudibleAccount).order_by(AudibleAccount.added_at.desc()).all()
    return {"accounts": [_account_to_dict(a) for a in accounts]}


@router.post("")
async def add_account(
    username: str = Form(...),
    auth_file: UploadFile = File(...),
    marketplace: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Add a new Audible account via auth file upload."""
    import json as json_mod

    existing = db.query(AudibleAccount).filter(AudibleAccount.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Account '{username}' already exists")

    content = await auth_file.read()
    try:
        auth_data = json_mod.loads(content)
        activation_bytes = auth_data.get("activation_bytes")
        if not activation_bytes:
            raise HTTPException(status_code=400, detail="Auth file missing activation_bytes")
    except json_mod.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON auth file")

    settings.audible_auth_path.mkdir(parents=True, exist_ok=True)
    auth_filename = f"{username}.json"
    auth_file_path = settings.audible_auth_path / auth_filename
    with open(auth_file_path, "wb") as f:
        f.write(content)

    account = AudibleAccount(
        username=username,
        auth_file_path=auth_filename,
        activation_bytes=activation_bytes,
        marketplace=marketplace,
        enabled=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return _account_to_dict(account)


@router.patch("/{account_id}")
async def patch_account(
    account_id: int,
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Toggle enabled/downloads_enabled for an account."""
    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if "enabled" in body:
        account.enabled = body["enabled"]

    if "downloads_enabled" in body:
        account.downloads_enabled = body["downloads_enabled"]
        if not account.downloads_enabled:
            db.query(DownloadQueue).filter(
                DownloadQueue.audible_account_id == account_id,
                DownloadQueue.status.in_([
                    DownloadStatus.PENDING, DownloadStatus.DOWNLOADING, DownloadStatus.DECRYPTING
                ]),
            ).delete(synchronize_session=False)

    db.commit()
    return _account_to_dict(account)


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete an Audible account."""
    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    db.delete(account)
    db.commit()
    return {"success": True}


@router.post("/{account_id}/sync")
async def sync_account(
    account_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Trigger account sync in background. Returns job_id."""
    from ...services.audible_sync import AudibleSyncService

    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if not account.enabled:
        raise HTTPException(status_code=400, detail="Account is disabled")

    def _sync_job(job_db, job):
        sync_service = AudibleSyncService(job_db)
        acct = job_db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
        return sync_service.sync_account(acct)

    job = BackgroundJobService.create_job(db, "sync", meta={"account_id": account_id})
    BackgroundJobService.submit(job.id, _sync_job)

    return {"job_id": job.id}


@router.post("/{account_id}/queue-all")
async def queue_all_books(
    account_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Queue all undownloaded books for download."""
    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    books_without_files = db.query(Book).filter(
        Book.audible_account_id == account_id,
        Book.file_path.is_(None),
    ).all()

    stats = {"queued": 0, "requeued": 0, "already_queued": 0, "skipped": 0}

    for book in books_without_files:
        if not book.download_enabled:
            stats["skipped"] += 1
            continue

        existing_entry = db.query(DownloadQueue).filter(
            DownloadQueue.book_id == book.id,
            DownloadQueue.download_type == DownloadType.BOOK,
        ).first()

        if existing_entry:
            if existing_entry.status in [DownloadStatus.PENDING, DownloadStatus.DOWNLOADING, DownloadStatus.DECRYPTING]:
                stats["already_queued"] += 1
                continue
            if existing_entry.status in [DownloadStatus.FAILED, DownloadStatus.COMPLETED]:
                existing_entry.status = DownloadStatus.PENDING
                existing_entry.attempts = 0
                existing_entry.error_message = None
                stats["requeued"] += 1
        else:
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
    return stats


@router.post("/login/generate-url")
async def generate_login_url(
    body: dict,
    current_user: User = Depends(require_admin),
):
    """Generate OAuth login URL for external browser authentication."""
    marketplace = body.get("marketplace", "us")
    with_username = body.get("with_username", False)

    session_id = secrets.token_urlsafe(32)

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

    _login_sessions[session_id] = {
        "code_verifier": code_verifier,
        "serial": serial,
        "marketplace": marketplace,
        "with_username": with_username,
        "domain": locale.domain,
    }

    return {"session_id": session_id, "oauth_url": oauth_url}


@router.post("/login/complete")
async def complete_login(
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Complete authentication using redirect URL from browser."""
    session_id = body.get("session_id")
    redirect_url = body.get("redirect_url")

    session_data = _login_sessions.get(session_id)
    if not session_data:
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(redirect_url)
    query_params = parse_qs(parsed.query)

    if "openid.oa2.authorization_code" not in query_params:
        raise HTTPException(status_code=400, detail="Invalid redirect URL")

    authorization_code = query_params["openid.oa2.authorization_code"][0]

    from audible.register import register

    register_data = register(
        authorization_code=authorization_code,
        code_verifier=session_data["code_verifier"],
        domain=session_data["domain"],
        serial=session_data["serial"],
        with_username=session_data["with_username"],
    )

    auth = Authenticator()
    auth.locale = Locale(session_data["marketplace"])
    auth._update_attrs(with_username=session_data["with_username"], **register_data)

    activation_bytes = auth.get_activation_bytes()
    user_info = auth.user_profile()
    username = user_info.get("name") or user_info.get("email") or session_data["serial"]

    existing = db.query(AudibleAccount).filter(AudibleAccount.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Account '{username}' already exists")

    settings.audible_auth_path.mkdir(parents=True, exist_ok=True)
    auth_filename = f"{username}.json"
    auth_file_path = settings.audible_auth_path / auth_filename
    auth.to_file(filename=auth_file_path, encryption=False)

    account = AudibleAccount(
        username=username,
        auth_file_path=auth_filename,
        activation_bytes=activation_bytes,
        marketplace=session_data["marketplace"],
        enabled=True,
    )
    db.add(account)
    db.commit()

    del _login_sessions[session_id]

    return {"success": True, "username": username}
