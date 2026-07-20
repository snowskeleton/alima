"""API v2 routes for server settings."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ...database import get_db
from ...dependencies import require_admin
from ...models import User
from ...services.image_processor import ImageProcessorService
from ...services.settings_service import SettingsService
from ...services.storage import normalise_endpoint
from ...utils.settings_cache import clear_settings_cache

router = APIRouter(prefix="/settings", tags=["Settings"])

SETTING_KEYS = [
    "app_name", "domain", "quick_sync_interval_minutes", "full_sync_interval_minutes",
    "download_quality", "max_concurrent_downloads", "session_expire_hours",
    "invite_expire_days", "default_feed_cover_url",
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "smtp_from_email", "smtp_from_name",
    "b2_enabled", "b2_bucket_name", "b2_endpoint_url",
    "b2_access_key_id", "b2_secret_access_key", "b2_signed_url_ttl_seconds",
]

# Secrets are returned masked and a blank submission means "leave unchanged",
# so saving the form without retyping them doesn't wipe the stored value.
SECRET_KEYS = {"smtp_password", "b2_secret_access_key"}

# Booleans reach here as either a GUI-written "true"/"false" or a Python bool
# stringified from the environment ("True"/"False"). Normalise on the way out so
# the client only ever has one form to compare against — otherwise an
# env-configured value renders as off, and saving would genuinely turn it off.
BOOL_KEYS = {"b2_enabled"}


def _normalise_bool(value) -> str:
    return "true" if str(value).strip().lower() in ("true", "1", "yes", "on") else "false"


@router.get("")
async def get_settings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get all server settings.

    Secrets are never sent to the client. They come back as an empty string,
    which the update handler treats as "leave unchanged".
    """
    settings_service = SettingsService(db)
    result = {}
    for key in SETTING_KEYS:
        if key in SECRET_KEYS:
            stored = settings_service.get(key)
            result[key] = "" if not stored else "********"
        elif key in BOOL_KEYS:
            result[key] = _normalise_bool(settings_service.get(key))
        else:
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

        # Copy-pasted credentials and hostnames routinely carry whitespace,
        # which boto3 and SMTP both reject in unhelpful ways.
        if isinstance(value, str):
            value = value.strip()

        # Blank or still-masked secret means "keep what's stored"
        if key in SECRET_KEYS and (not value or value == "********"):
            continue

        # Backblaze displays the endpoint without a scheme; boto3 requires one.
        if key == "b2_endpoint_url" and value:
            value = normalise_endpoint(value)

        if value == "":
            value = None

        if key.startswith("smtp_"):
            category = "email"
        elif key.startswith("b2_"):
            category = "storage"
        else:
            category = "general"

        settings_service.set(
            key=key,
            value=value,
            category=category,
            user_id=current_user.id,
        )

    # Settings are read through an in-memory cache, so without this the new
    # values wouldn't take effect until the process restarted. This also
    # invalidates the cached B2 client, since it's keyed on the config values.
    clear_settings_cache()

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


@router.post("/test-b2")
async def test_b2(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Verify the saved Backblaze B2 settings by reaching the bucket.

    Uses head_bucket, which confirms the endpoint, credentials and bucket name
    all line up without transferring anything.
    """
    from ...services.storage import get_storage_service

    # Test what's actually stored, not what this worker happens to have cached
    # from up to CACHE_TTL_SECONDS ago.
    clear_settings_cache()

    storage = get_storage_service()
    if not storage:
        raise HTTPException(
            status_code=400,
            detail="B2 is disabled or its configuration is incomplete. Save your settings first.",
        )

    try:
        storage.test_connection()
    except Exception as e:
        # botocore messages are the useful part here (403 = bad key or no
        # permission on this bucket, 404 = bucket name or region is wrong)
        raise HTTPException(status_code=400, detail=f"B2 connection failed: {e}")

    return {"success": True, "message": "Connected to B2 successfully."}


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
