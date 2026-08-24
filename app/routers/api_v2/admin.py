"""API v2 routes for admin operations."""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ...database import get_db
from ...dependencies import require_admin, require_admin_session
from ...models import ApiKey, User
from ...services.background_jobs import BackgroundJobService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin"])


@router.post("/sync/force-refresh-metadata")
async def force_refresh_metadata(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Force refresh all book metadata in background."""
    from ...services.audible_sync import AudibleSyncService

    def _refresh_job(job_db, job):
        sync_service = AudibleSyncService(job_db)
        return sync_service.force_refresh_all_metadata()

    job = BackgroundJobService.create_job(db, "metadata_refresh")
    BackgroundJobService.submit(job.id, _refresh_job)

    return {"job_id": job.id}


@router.get("/api-keys")
async def list_api_keys(
    current_user: User = Depends(require_admin_session),
    db: Session = Depends(get_db),
):
    """List API keys for current user.

    Session-only: an API key cannot enumerate API keys.
    """
    keys = db.query(ApiKey).filter(ApiKey.user_id == current_user.id).order_by(ApiKey.created_at.desc()).all()
    return {
        "api_keys": [
            {
                "id": k.id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                # null means never used; keys created before usage tracking
                # stay null rather than reporting a use that never happened
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                # null means the key never expires
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "is_expired": k.is_expired,
            }
            for k in keys
        ]
    }


@router.post("/api-keys")
async def create_api_key(
    body: dict,
    current_user: User = Depends(require_admin_session),
    db: Session = Depends(get_db),
):
    """Generate a new API key.

    Session-only: an API key cannot mint further keys, so a leaked key cannot
    issue itself a permanent replacement that survives its own revocation.

    Accepts an optional `expires_in_days`; omitting it creates a key that never
    expires, matching how keys behaved before expiry was supported.
    """
    name = body.get("name", "Unnamed Key")

    expires_at = None
    expires_in_days = body.get("expires_in_days")
    if expires_in_days is not None:
        try:
            days = int(expires_in_days)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="expires_in_days must be a number")
        if days < 1:
            raise HTTPException(status_code=400, detail="expires_in_days must be at least 1")
        expires_at = datetime.utcnow() + timedelta(days=days)

    raw_key = secrets.token_urlsafe(32)
    key_prefix = raw_key[:8]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = ApiKey(
        user_id=current_user.id,
        name=name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        expires_at=expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    logger.info(f"API key created: '{name}' by {current_user.email}")

    return {
        "key": raw_key,
        "key_id": api_key.id,
        "name": api_key.name,
        "prefix": key_prefix,
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
    }


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: int,
    current_user: User = Depends(require_admin_session),
    db: Session = Depends(get_db),
):
    """Revoke an API key.

    Session-only, like the rest of key management.
    """
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id, ApiKey.user_id == current_user.id
    ).first()

    if not api_key:
        return JSONResponse(status_code=404, content={"error": "API key not found"})

    key_name = api_key.name
    db.delete(api_key)
    db.commit()

    logger.info(f"API key revoked: '{key_name}' by {current_user.email}")
    return {"success": True}
