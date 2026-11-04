"""API v2 routes for Audible account management."""

from datetime import datetime, timedelta

from audible import Authenticator
from jose import JWTError, jwt
from audible.localization import Locale
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ...config import settings
from ...database import get_db
from ...dependencies import require_admin
from ...models import AudibleAccount, Book, DownloadQueue, DownloadStatus, DownloadType, User
from ...schemas import DatabaseId
from ...services.background_jobs import BackgroundJobService

router = APIRouter(prefix="/accounts", tags=["Accounts"])

# OAuth login sessions are carried in a signed, short-lived token rather than in
# process memory: the app runs under several gunicorn workers, so the worker that
# handles /login/complete is usually not the one that handled /login/generate-url.
# Generous expiry: the usual flow is to send the login URL to the account's owner
# and wait for them to send the redirect URL back, which can take hours.
LOGIN_SESSION_EXPIRE_MINUTES = 60 * 24 * 7


# Since ~2026-10-21 Audible denies download licenses (AYCL / CustomerThrottled)
# to devices registered with the old iPhone profile, which used a 32-character
# hex serial. audible 0.13.1 registers with a 40-character serial and a current
# app profile. The profile is fixed at registration, so an account registered
# the old way has to be re-authenticated. See mkb79/Audible#909.
CURRENT_DEVICE_SERIAL_LENGTH = 40


def _needs_reauth(account: AudibleAccount) -> bool:
    """True when the account's device was registered with the outdated profile.

    Reads the serial straight from the auth file rather than loading an
    Authenticator, so listing accounts stays cheap. An unreadable file counts as
    needing re-authentication: that account can't download either way.
    """
    import json as json_mod

    try:
        with open(settings.audible_auth_path / account.auth_file_path) as f:
            data = json_mod.load(f)
        serial = (data.get("device_info") or {}).get("device_serial_number") or ""
    except (OSError, ValueError, AttributeError):
        return True
    return len(serial) != CURRENT_DEVICE_SERIAL_LENGTH


def _account_to_dict(account: AudibleAccount) -> dict:
    return {
        "id": account.id,
        "username": account.username,
        "marketplace": account.marketplace,
        "enabled": account.enabled,
        "downloads_enabled": account.downloads_enabled,
        "needs_reauth": _needs_reauth(account),
        "previous_devices": len(_previous_device_files(account.id)),
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
        # json.loads happily returns a bare int, str, or list for input like
        # "1", none of which have .get() — that was a 500 on a malformed upload.
        if not isinstance(auth_data, dict):
            raise HTTPException(
                status_code=400, detail="Auth file must contain a JSON object"
            )
        activation_bytes = auth_data.get("activation_bytes")
        if not activation_bytes:
            raise HTTPException(status_code=400, detail="Auth file missing activation_bytes")
    except (json_mod.JSONDecodeError, UnicodeDecodeError):
        # UnicodeDecodeError as well as JSONDecodeError: json.loads decodes the
        # raw upload bytes as UTF-8 first, so a binary file raises before it ever
        # reaches the JSON parser.
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
    account_id: DatabaseId,
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
    account_id: DatabaseId,
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
    account_id: DatabaseId,
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
    account_id: DatabaseId,
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
    db: Session = Depends(get_db),
):
    """Generate OAuth login URL for external browser authentication.

    Pass ``account_id`` to re-authenticate an existing account instead of adding
    a new one: the marketplace then comes from that account, and completing the
    login replaces its device registration in place.
    """
    marketplace = body.get("marketplace", "us")
    with_username = body.get("with_username", False)

    reauth_account_id = body.get("account_id")
    if reauth_account_id is not None:
        if not isinstance(reauth_account_id, int) or isinstance(reauth_account_id, bool):
            raise HTTPException(status_code=400, detail="account_id must be an integer")
        account = db.query(AudibleAccount).filter(AudibleAccount.id == reauth_account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        marketplace = account.marketplace.lower()

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

    session_id = jwt.encode(
        {
            "code_verifier": code_verifier.decode() if isinstance(code_verifier, bytes) else code_verifier,
            "serial": serial,
            "marketplace": marketplace,
            "with_username": with_username,
            "domain": locale.domain,
            "reauth_account_id": reauth_account_id,
            "exp": datetime.utcnow() + timedelta(minutes=LOGIN_SESSION_EXPIRE_MINUTES),
        },
        settings.secret_key,
        algorithm="HS256",
    )

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

    try:
        session_data = jwt.decode(session_id, settings.secret_key, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    from urllib.parse import parse_qs, urlparse
    parsed = urlparse((redirect_url or "").strip())
    query_params = parse_qs(parsed.query)

    if "openid.oa2.authorization_code" not in query_params:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid redirect URL: no openid.oa2.authorization_code found. "
                "Copy the full URL of the page you land on after signing in."
            ),
        )

    authorization_code = query_params["openid.oa2.authorization_code"][0]

    from audible.register import register

    try:
        register_data = register(
            authorization_code=authorization_code,
            code_verifier=session_data["code_verifier"].encode(),
            domain=session_data["domain"],
            serial=session_data["serial"],
            with_username=session_data["with_username"],
        )
    except Exception as exc:
        # Most often a redirect URL that was already used, or one from an older
        # login attempt. Was a 500 before.
        import logging
        logging.getLogger(__name__).warning("Device registration failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=(
                "Amazon didn't accept that sign-in. The redirect URL may already have been "
                "used or be from an older login. Start over and sign in again."
            ),
        )

    auth = Authenticator()
    auth.locale = Locale(session_data["marketplace"])
    auth._update_attrs(with_username=session_data["with_username"], **register_data)

    return finish_registration(
        db,
        auth,
        marketplace=session_data["marketplace"],
        reauth_account_id=session_data.get("reauth_account_id"),
    )


def finish_registration(
    db: Session, auth: Authenticator, *, marketplace: str, reauth_account_id: int | None
) -> dict:
    """Put a freshly registered device to use: re-auth an account, or add one.

    Shared by the paste-the-URL login and the device-code sign-in links. If the
    device can't be used, it is deregistered again before the error is raised,
    so refusals don't leave strays in the person's Amazon device list.
    """
    if reauth_account_id is not None:
        return _complete_reauth(db, reauth_account_id, auth)
    return _create_account(db, auth, marketplace)


def _create_account(db: Session, auth: Authenticator, marketplace: str) -> dict:
    try:
        activation_bytes = auth.get_activation_bytes()
        user_info = auth.user_profile()
    except Exception as exc:
        _deregister_quietly(auth)
        raise HTTPException(status_code=502, detail=f"Couldn't read the new account from Audible: {exc}")
    username = (
        user_info.get("name")
        or user_info.get("email")
        or (auth.device_info or {}).get("device_serial_number")
    )

    existing = db.query(AudibleAccount).filter(AudibleAccount.username == username).first()
    if existing:
        _deregister_quietly(auth)
        raise HTTPException(
            status_code=400,
            detail=f"Account '{username}' already exists. Use Re-authenticate on it instead.",
        )

    settings.audible_auth_path.mkdir(parents=True, exist_ok=True)
    auth_filename = f"{username}.json"
    auth_file_path = settings.audible_auth_path / auth_filename
    auth.to_file(filename=auth_file_path, encryption=False)

    account = AudibleAccount(
        username=username,
        auth_file_path=auth_filename,
        activation_bytes=activation_bytes,
        marketplace=marketplace,
        enabled=True,
    )
    db.add(account)
    db.commit()

    return {"success": True, "username": username}


def _customer_id(auth: Authenticator) -> str | None:
    return (auth.customer_info or {}).get("user_id")


def _deregister_quietly(auth: Authenticator) -> str | None:
    """Deregister ``auth``'s device. Returns an error message instead of raising."""
    import logging

    try:
        auth.deregister_device()
    except Exception as exc:  # network, expired refresh token, Amazon error...
        logging.getLogger(__name__).warning("Device deregistration failed: %s", exc)
        return str(exc) or type(exc).__name__
    return None


def _previous_devices_dir():
    return settings.audible_auth_path / "previous_devices"


def _previous_device_files(account_id: int) -> list:
    """Auth files of devices an account was re-authenticated away from.

    Named ``<account id>-<serial>.json``. They are kept only so the old device
    can be deregistered on request, and are deleted once it has been.
    """
    directory = _previous_devices_dir()
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"{account_id}-*.json"))


def _serial(auth: Authenticator | None) -> str | None:
    if auth is None:
        return None
    return (auth.device_info or {}).get("device_serial_number")


def _complete_reauth(db: Session, account_id: int, new_auth: Authenticator) -> dict:
    """Swap an existing account onto the freshly registered device ``new_auth``.

    The old device is *not* deregistered here. Its auth file is set aside in
    ``previous_devices/`` so it can be deregistered separately, from
    ``POST /accounts/{id}/deregister-previous-devices``, once the new
    registration is known to work.
    """
    import os
    import re
    import shutil

    def discard_new_device(detail: str, status_code: int = 400):
        # The new device is already registered on Amazon's side. Don't leave it
        # orphaned in the user's device list when we refuse to use it.
        _deregister_quietly(new_auth)
        raise HTTPException(status_code=status_code, detail=detail)

    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        discard_new_device("Account not found", status_code=404)

    auth_file_path = settings.audible_auth_path / account.auth_file_path
    try:
        old_auth = Authenticator.from_file(str(auth_file_path))
    except Exception:
        old_auth = None

    # Signing in with a different Amazon account would otherwise silently
    # repoint this account (and all its books) at someone else's library.
    old_customer = _customer_id(old_auth) if old_auth else None
    new_customer = _customer_id(new_auth)
    if old_customer and new_customer != old_customer:
        discard_new_device(
            f"That login belongs to a different Amazon account than '{account.username}'. "
            "Sign in with the same Amazon account this one was added with."
        )

    try:
        activation_bytes = new_auth.get_activation_bytes()
    except Exception as exc:
        discard_new_device(f"Could not fetch activation bytes for the new device: {exc}", 502)

    # Keep the old device's credentials: they are the only way to deregister it
    # later. An unreadable file can't deregister anything, so it isn't kept.
    old_serial = _serial(old_auth)
    if old_serial and old_serial != _serial(new_auth) and re.fullmatch(r"[A-Za-z0-9]+", old_serial):
        _previous_devices_dir().mkdir(parents=True, exist_ok=True)
        shutil.copyfile(auth_file_path, _previous_devices_dir() / f"{account.id}-{old_serial}.json")

    # Write to a temp file and rename over the old one, so a download or sync
    # reading the auth file mid-swap sees either the old file or the new one.
    settings.audible_auth_path.mkdir(parents=True, exist_ok=True)
    tmp_path = auth_file_path.with_name(auth_file_path.name + ".new")
    new_auth.to_file(filename=tmp_path, encryption=False)
    os.replace(tmp_path, auth_file_path)

    account.activation_bytes = activation_bytes
    db.commit()

    return {
        "success": True,
        "username": account.username,
        "reauthenticated": True,
        "previous_devices": len(_previous_device_files(account.id)),
    }


@router.post("/{account_id}/deregister-previous-devices")
async def deregister_previous_devices(
    account_id: DatabaseId,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deregister the devices this account was re-authenticated away from.

    Each one that Amazon confirms is removed has its saved auth file deleted.
    The account's current device is never touched, even if a stale copy of it
    ended up among the previous devices.
    """
    account = db.query(AudibleAccount).filter(AudibleAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        current_serial = _serial(
            Authenticator.from_file(str(settings.audible_auth_path / account.auth_file_path))
        )
    except Exception:
        current_serial = None
    if not current_serial:
        # Without knowing the current device we can't rule out deregistering it.
        raise HTTPException(
            status_code=409,
            detail="The account's current auth file can't be read, so its old devices weren't touched.",
        )

    removed = 0
    failed = []
    for path in _previous_device_files(account.id):
        try:
            old_auth = Authenticator.from_file(str(path))
        except Exception as exc:
            failed.append({"device": path.stem.split("-", 1)[-1][-6:], "error": f"unreadable: {exc}"})
            continue
        serial = _serial(old_auth) or ""
        if serial == current_serial:
            path.unlink()  # a copy of the live device, not an old one
            continue
        error = _deregister_quietly(old_auth)
        if error:
            failed.append({"device": serial[-6:], "error": error})
        else:
            path.unlink()
            removed += 1

    return {
        "removed": removed,
        "failed": failed,
        "previous_devices": len(_previous_device_files(account.id)),
    }
