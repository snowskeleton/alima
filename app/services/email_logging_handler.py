"""Custom logging handler that sends email notifications for errors and warnings."""

import asyncio
import logging
import traceback
from typing import Optional


class EmailNotificationHandler(logging.Handler):
    """
    Custom logging handler that sends email notifications for ERROR and WARNING level logs.

    This handler runs asynchronously to avoid blocking the application when sending emails.
    """

    def __init__(self, level=logging.WARNING):
        """
        Initialize the email notification handler.

        Args:
            level: Minimum logging level to handle (default: WARNING)
        """
        super().__init__(level)
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record by sending an email notification.

        Args:
            record: The log record to process
        """
        try:
            # Don't send notifications for our own email service to avoid loops
            if record.name.startswith('app.services.email'):
                return

            # Format the log message
            error_message = self.format(record)

            # Get stack trace if exception info is available
            error_details = None
            if record.exc_info:
                error_details = ''.join(traceback.format_exception(*record.exc_info))

            # Send email asynchronously without blocking
            # We use asyncio.create_task if we have an event loop, otherwise we skip
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule the email to be sent
                    asyncio.create_task(self._send_email(
                        record.levelname,
                        error_message,
                        error_details
                    ))
                else:
                    # If no loop is running, run it in a new loop
                    # This handles cases where logging happens outside async context
                    asyncio.run(self._send_email(
                        record.levelname,
                        error_message,
                        error_details
                    ))
            except RuntimeError:
                # No event loop available, create one
                asyncio.run(self._send_email(
                    record.levelname,
                    error_message,
                    error_details
                ))

        except Exception:
            # Never let the handler crash the application
            # Just use handleError to log the exception
            self.handleError(record)

    async def _send_email(
        self,
        error_level: str,
        error_message: str,
        error_details: Optional[str] = None
    ) -> None:
        """
        Send the email notification asynchronously.

        Args:
            error_level: Log level (ERROR, WARNING, CRITICAL)
            error_message: The formatted log message
            error_details: Optional stack trace or additional details
        """
        try:
            from .email_service import EmailService
            await EmailService.send_error_notification(
                error_level,
                error_message,
                error_details
            )
        except Exception as e:
            # Log the error but don't propagate it
            # Use print to avoid infinite loop
            print(f"Failed to send error notification email: {e}")
