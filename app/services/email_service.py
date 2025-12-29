"""Email service for sending invite emails."""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib

from ..config import settings
from ..database import SessionLocal

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP."""

    def __init__(self):
        """Initialize email service and load settings."""
        self._load_settings()

    def _load_settings(self):
        """Load SMTP settings from database or config."""
        # Try to load from database first
        try:
            from .settings_service import SettingsService

            db = SessionLocal()
            settings_service = SettingsService(db)

            # Load SMTP settings from database
            self.smtp_host = settings_service.get("smtp_host") or settings.smtp_host
            self.smtp_port = int(settings_service.get("smtp_port") or settings.smtp_port or 587)
            self.smtp_username = settings_service.get("smtp_username") or settings.smtp_user
            self.smtp_password = settings_service.get("smtp_password") or settings.smtp_password
            self.smtp_from_email = settings_service.get("smtp_from_email") or settings.smtp_from
            self.smtp_from_name = settings_service.get("smtp_from_name") or settings.app_name

            # Load general settings
            self.app_name = settings_service.get("app_name") or settings.app_name
            self.domain = settings_service.get("domain") or settings.domain
            self.invite_expire_days = int(settings_service.get("invite_expire_days") or settings.invite_expire_days or 7)

            db.close()
        except Exception as e:
            logger.warning(f"Failed to load settings from database, using config: {e}")
            # Fallback to config
            self.smtp_host = settings.smtp_host
            self.smtp_port = settings.smtp_port
            self.smtp_username = settings.smtp_user
            self.smtp_password = settings.smtp_password
            self.smtp_from_email = settings.smtp_from
            self.smtp_from_name = settings.app_name
            self.app_name = settings.app_name
            self.domain = settings.domain
            self.invite_expire_days = settings.invite_expire_days

    async def send_invite_email(
        self, recipient_email: str, invite_token: str, invited_by: str
    ) -> bool:
        """
        Send an invite email to a new user.

        Args:
            recipient_email: Email address to send invite to
            invite_token: Unique invite token for registration
            invited_by: Email of the admin who sent the invite

        Returns:
            True if email sent successfully, False otherwise
        """
        # Skip if SMTP not configured
        if not self.smtp_host or not self.smtp_from_email:
            logger.warning(
                f"SMTP not configured. Invite URL for {recipient_email}: "
                f"{self.domain}/auth/accept-invite?token={invite_token}"
            )
            return False

        # Build invite URL
        invite_url = f"{self.domain}/auth/accept-invite?token={invite_token}"

        # Create email message
        subject = f"You've been invited to {self.app_name}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 24px;
                    background-color: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                    margin: 20px 0;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #ddd;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Welcome to {self.app_name}!</h2>
                <p>{invited_by} has invited you to join {self.app_name}, an audiobook library manager.</p>
                <p>Click the button below to accept your invite and create your account:</p>
                <a href="{invite_url}" class="button">Accept Invite</a>
                <p>Or copy and paste this link into your browser:</p>
                <p><a href="{invite_url}">{invite_url}</a></p>
                <div class="footer">
                    <p>This invite will expire in {self.invite_expire_days} days.</p>
                    <p>If you didn't expect this invitation, you can safely ignore this email.</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
Welcome to {self.app_name}!

{invited_by} has invited you to join {self.app_name}, an audiobook library manager.

Accept your invite by visiting this link:
{invite_url}

This invite will expire in {self.invite_expire_days} days.

If you didn't expect this invitation, you can safely ignore this email.
        """

        try:
            # Create message
            message = MIMEMultipart("alternative")
            from_header = f"{self.smtp_from_name} <{self.smtp_from_email}>" if self.smtp_from_name else self.smtp_from_email
            message["From"] = from_header
            message["To"] = recipient_email
            message["Subject"] = subject

            # Attach both plain text and HTML versions
            message.attach(MIMEText(text_body, "plain"))
            message.attach(MIMEText(html_body, "html"))

            # Send email
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_username,
                password=self.smtp_password,
                start_tls=True,
            )

            logger.info(f"Invite email sent successfully to {recipient_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send invite email to {recipient_email}: {e}")
            return False

    @staticmethod
    async def send_password_reset_email(
        recipient_email: str, reset_token: str
    ) -> bool:
        """
        Send a password reset email.

        Args:
            recipient_email: Email address to send reset link to
            reset_token: Unique reset token

        Returns:
            True if email sent successfully, False otherwise
        """
        # Get settings from database
        from .settings_service import SettingsService
        from ..database import SessionLocal

        db = SessionLocal()
        try:
            settings_service = SettingsService(db)
            domain = SettingsService.get_domain(db)
            smtp_host = settings_service.get("smtp_host") or settings.smtp_host
            smtp_from = settings_service.get("smtp_from_email") or settings.smtp_from
            smtp_port = int(settings_service.get("smtp_port") or settings.smtp_port or 587)
            smtp_username = settings_service.get("smtp_username") or settings.smtp_user
            smtp_password = settings_service.get("smtp_password") or settings.smtp_password
            smtp_from_name = settings_service.get("smtp_from_name") or settings.app_name
            app_name = settings_service.get("app_name") or settings.app_name
        finally:
            db.close()

        # Skip if SMTP not configured
        if not smtp_host or not smtp_from:
            logger.warning(
                f"SMTP not configured. Reset URL for {recipient_email}: "
                f"{domain}/auth/reset-password?token={reset_token}"
            )
            return False

        # Build reset URL
        reset_url = f"{domain}/auth/reset-password?token={reset_token}"

        # Create email message
        subject = f"{app_name} - Password Reset"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 24px;
                    background-color: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                    margin: 20px 0;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #ddd;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Password Reset Request</h2>
                <p>You requested to reset your password for {app_name}.</p>
                <p>Click the button below to reset your password:</p>
                <a href="{reset_url}" class="button">Reset Password</a>
                <p>Or copy and paste this link into your browser:</p>
                <p><a href="{reset_url}">{reset_url}</a></p>
                <div class="footer">
                    <p>This link will expire in 24 hours.</p>
                    <p>If you didn't request a password reset, you can safely ignore this email.</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
Password Reset Request

You requested to reset your password for {app_name}.

Reset your password by visiting this link:
{reset_url}

This link will expire in 24 hours.

If you didn't request a password reset, you can safely ignore this email.
        """

        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["From"] = f"{smtp_from_name} <{smtp_from}>" if smtp_from_name else smtp_from
            message["To"] = recipient_email
            message["Subject"] = subject

            # Attach both plain text and HTML versions
            message.attach(MIMEText(text_body, "plain"))
            message.attach(MIMEText(html_body, "html"))

            # Send email
            await aiosmtplib.send(
                message,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_username,
                password=smtp_password,
                start_tls=True,
            )

            logger.info(f"Password reset email sent successfully to {recipient_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send password reset email to {recipient_email}: {e}")
            return False

    async def send_test_email(self, recipient_email: str) -> bool:
        """
        Send a test email to verify SMTP settings.

        Args:
            recipient_email: Email address to send test to

        Returns:
            True if email sent successfully, False otherwise
        """
        # Skip if SMTP not configured
        if not self.smtp_host or not self.smtp_from_email:
            logger.warning("SMTP not configured. Cannot send test email.")
            return False

        # Create email message
        subject = f"{self.app_name} - Test Email"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .success {{
                    background-color: #d4edda;
                    border: 1px solid #c3e6cb;
                    color: #155724;
                    padding: 15px;
                    border-radius: 4px;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>SMTP Test Successful!</h2>
                <div class="success">
                    <p><strong>✓ Your email settings are working correctly.</strong></p>
                </div>
                <p>This is a test email from {self.app_name}.</p>
                <p>If you received this email, it means your SMTP configuration is set up correctly and {self.app_name} can send emails.</p>
                <p><strong>Email Configuration:</strong></p>
                <ul>
                    <li>SMTP Host: {self.smtp_host}</li>
                    <li>SMTP Port: {self.smtp_port}</li>
                    <li>From Email: {self.smtp_from_email}</li>
                </ul>
            </div>
        </body>
        </html>
        """

        text_body = f"""
SMTP Test Successful!

This is a test email from {self.app_name}.

If you received this email, it means your SMTP configuration is set up correctly and {self.app_name} can send emails.

Email Configuration:
- SMTP Host: {self.smtp_host}
- SMTP Port: {self.smtp_port}
- From Email: {self.smtp_from_email}
        """

        try:
            # Create message
            message = MIMEMultipart("alternative")
            from_header = f"{self.smtp_from_name} <{self.smtp_from_email}>" if self.smtp_from_name else self.smtp_from_email
            message["From"] = from_header
            message["To"] = recipient_email
            message["Subject"] = subject

            # Attach both plain text and HTML versions
            message.attach(MIMEText(text_body, "plain"))
            message.attach(MIMEText(html_body, "html"))

            # Send email
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_username,
                password=self.smtp_password,
                start_tls=True,
            )

            logger.info(f"Test email sent successfully to {recipient_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send test email to {recipient_email}: {e}")
            return False
