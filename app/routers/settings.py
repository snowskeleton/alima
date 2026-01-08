"""Routes for server settings management."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models import User
from ..services.settings_service import SettingsService
from ..services.image_processor import ImageProcessorService

router = APIRouter(prefix="/admin/settings", tags=["Admin - Settings"])
templates = Jinja2Templates(directory="app/templates")


# Define setting definitions with categories and descriptions
# Order matters - general settings first, then email
SETTING_DEFINITIONS = {
    "general": [
        {
            "key": "app_name",
            "label": "Application Name",
            "type": "text",
            "placeholder": "Alima",
            "description": "Name displayed throughout the application",
        },
        {
            "key": "domain",
            "label": "Domain URL",
            "type": "url",
            "placeholder": "https://alima.example.com",
            "description": "Full URL where this application is hosted (use https:// for SSL)",
        },
        {
            "key": "quick_sync_interval_minutes",
            "label": "Quick Sync Interval (minutes)",
            "type": "number",
            "placeholder": "1",
            "description": "How often to check for new books from Audible (in minutes)",
        },
        {
            "key": "full_sync_interval_minutes",
            "label": "Full Sync Interval (minutes)",
            "type": "number",
            "placeholder": "1440",
            "description": "How often to perform a complete library refresh from Audible (1440 = 24 hours)",
        },
        {
            "key": "download_quality",
            "label": "Download Quality",
            "type": "select",
            "placeholder": "High",
            "description": "Audio quality for downloads",
            "options": ["High", "Normal"],
        },
        {
            "key": "max_concurrent_downloads",
            "label": "Max Concurrent Downloads",
            "type": "number",
            "placeholder": "3",
            "description": "Maximum number of parallel downloads (higher = faster but uses more bandwidth)",
        },
        {
            "key": "session_expire_hours",
            "label": "Session Expiration (hours)",
            "type": "number",
            "placeholder": "168",
            "description": "How long user sessions last before requiring re-login (168 = 7 days)",
        },
        {
            "key": "invite_expire_days",
            "label": "Invite Expiration (days)",
            "type": "number",
            "placeholder": "7",
            "description": "Number of days before invitation links expire",
        },
        {
            "key": "default_feed_cover_url",
            "label": "Default Feed Cover Image",
            "type": "file",
            "placeholder": "",
            "description": "Default cover image for podcast feeds without custom artwork",
        },
    ],
    "email": [
        {
            "key": "smtp_host",
            "label": "SMTP Host",
            "type": "text",
            "placeholder": "smtp.gmail.com",
            "description": "SMTP server hostname",
        },
        {
            "key": "smtp_port",
            "label": "SMTP Port",
            "type": "number",
            "placeholder": "587",
            "description": "SMTP server port (usually 587 for TLS or 465 for SSL)",
        },
        {
            "key": "smtp_username",
            "label": "SMTP Username",
            "type": "text",
            "placeholder": "your-email@gmail.com",
            "description": "SMTP authentication username (usually your email)",
        },
        {
            "key": "smtp_password",
            "label": "SMTP Password",
            "type": "password",
            "autocomplete": "new-password",
            "placeholder": "••••••••",
            "description": "SMTP authentication password (encrypted in database). For Gmail app passwords, enter all 16 characters without spaces.",
        },
        {
            "key": "smtp_from_email",
            "label": "From Email",
            "type": "email",
            "placeholder": "noreply@example.com",
            "description": "Email address to send from",
        },
        {
            "key": "smtp_from_name",
            "label": "From Name",
            "type": "text",
            "placeholder": "Alima",
            "description": "Display name for sent emails",
        },
    ],
}


@router.get("", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Display server settings page."""
    from ..utils.flash import get_flashed_messages

    settings_service = SettingsService(db)

    # Get current settings values
    current_settings = {}
    for category, definitions in SETTING_DEFINITIONS.items():
        for setting_def in definitions:
            key = setting_def["key"]
            current_settings[key] = settings_service.get(key)

    return templates.TemplateResponse(
        request=request,
        name="admin/settings.html",
        context={
            "current_user": current_user,
            "setting_definitions": SETTING_DEFINITIONS,
            "current_settings": current_settings,
            "messages": get_flashed_messages(request),
        },
    )


@router.post("/update")
async def update_settings(
    request: Request,
    default_feed_cover_file: UploadFile = File(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update server settings."""
    settings_service = SettingsService(db)
    image_processor = ImageProcessorService()

    # Get form data
    form_data = await request.form()

    # Handle file upload for default feed cover
    if default_feed_cover_file and default_feed_cover_file.filename:
        try:
            # Delete old cover if exists
            old_cover_path = settings_service.get("default_feed_cover_url")
            if old_cover_path:
                image_processor.delete_cover(old_cover_path)

            # Process and save new cover
            cover_path = await image_processor.process_feed_cover(default_feed_cover_file)
            settings_service.set(
                key="default_feed_cover_url",
                value=cover_path,
                category="general",
                description="Default cover image for podcast feeds without custom artwork",
                user_id=current_user.id,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # Update all other settings from the form
    for category, definitions in SETTING_DEFINITIONS.items():
        for setting_def in definitions:
            key = setting_def["key"]

            # Skip file type (already handled above)
            if setting_def["type"] == "file":
                continue

            value = form_data.get(key)

            # Skip empty passwords (means "don't change")
            if setting_def["type"] == "password" and not value:
                continue

            # Convert empty strings to None
            if value == "":
                value = None

            # Save setting
            settings_service.set(
                key=key,
                value=value,
                category=category,
                description=setting_def["description"],
                user_id=current_user.id,
            )

    from ..utils.flash import flash
    flash(request, "Settings saved successfully!", "success")
    return RedirectResponse(
        url="/admin/settings", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/remove-default-cover")
async def remove_default_cover(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove the default feed cover image."""
    from ..utils.flash import flash

    settings_service = SettingsService(db)
    image_processor = ImageProcessorService()

    # Get current cover path
    cover_path = settings_service.get("default_feed_cover_url")

    if cover_path:
        # Delete the file
        image_processor.delete_cover(cover_path)

        # Remove from settings
        settings_service.set(
            key="default_feed_cover_url",
            value=None,
            category="general",
            description="Default cover image for podcast feeds without custom artwork",
            user_id=current_user.id,
        )
        flash(request, "Default cover removed successfully", "success")

    return RedirectResponse(url="/admin/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/test-email")
async def test_email(
    request: Request,
    recipient_email: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Send a test email to verify SMTP settings."""
    from ..services.email_service import EmailService
    from ..utils.flash import flash

    try:
        email_service = EmailService()
        success = await email_service.send_test_email(recipient_email)

        if success:
            flash(request, f"Test email sent successfully to {recipient_email}!", "success")
        else:
            flash(request, "Failed to send test email. Please check your SMTP settings.", "error")

        return RedirectResponse(
            url="/admin/settings",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        flash(request, f"Failed to send test email: {str(e)}", "error")
        return RedirectResponse(
            url="/admin/settings",
            status_code=status.HTTP_303_SEE_OTHER
        )
