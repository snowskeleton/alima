"""API v2 routes for server settings."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ...database import get_db
from ...dependencies import require_admin
from ...models import User
from ...services.image_processor import ImageProcessorService
from ...services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["Settings"])

SETTING_KEYS = [
    "app_name", "domain", "quick_sync_interval_minutes", "full_sync_interval_minutes",
    "download_quality", "max_concurrent_downloads", "session_expire_hours",
    "invite_expire_days", "default_feed_cover_url",
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "smtp_from_email", "smtp_from_name",
]


@router.get("")
async def get_settings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get all server settings."""
    settings_service = SettingsService(db)
    result = {}
    for key in SETTING_KEYS:
        result[key] = settings_service.get(key)
    return {"settings": result}


@router.put("")
async def update_settings(
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update server settings."""
    settings_service = SettingsService(db)

    for key, value in body.items():
        if key not in SETTING_KEYS:
            continue
        if key == "default_feed_cover_url":
            continue
        if key == "smtp_password" and not value:
            continue

        if value == "":
            value = None

        category = "email" if key.startswith("smtp_") else "general"
        settings_service.set(
            key=key,
            value=value,
            category=category,
            user_id=current_user.id,
        )

    return {"success": True}


@router.post("/test-email")
async def test_email(
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Send a test email."""
    from ...services.email_service import EmailService

    recipient = body.get("recipient_email")
    if not recipient:
        raise HTTPException(status_code=400, detail="recipient_email required")

    email_service = EmailService()
    success = await email_service.send_test_email(recipient)

    return {"success": success}


@router.delete("/default-cover")
async def remove_default_cover(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove the default feed cover image."""
    settings_service = SettingsService(db)
    cover_path = settings_service.get("default_feed_cover_url")

    if cover_path:
        ImageProcessorService().delete_cover(cover_path)
        settings_service.set(
            key="default_feed_cover_url",
            value=None,
            category="general",
            user_id=current_user.id,
        )

    return {"success": True}
