"""Tests to verify email mocking is working correctly."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User


@pytest.mark.unit
class TestEmailMocking:
    """Test that emails are properly mocked during tests."""

    def test_email_service_is_mocked(self, mock_email_service):
        """Verify that email service is mocked."""
        assert mock_email_service is not None
        assert "send_invite_email" in mock_email_service
        assert "send_test_email" in mock_email_service
        assert "send_password_reset_email" in mock_email_service

    def test_send_invite_does_not_send_real_email(
        self, admin_client: TestClient, mock_email_service
    ):
        """Verify that sending an invite does not send real emails."""
        # Send an invite
        response = admin_client.post(
            "/admin/invites/send",
            data={
                "email": "test@example.com",
                "role": "user",
            },
            follow_redirects=False,
        )

        # Should succeed
        assert response.status_code == 303

        # Verify email mock was called (but no real email sent)
        mock_email_service["send_invite_email"].assert_called_once()

        # Get the call arguments
        call_args = mock_email_service["send_invite_email"].call_args
        assert call_args.kwargs["recipient_email"] == "test@example.com"

    def test_smtp_disabled_in_test_environment(self):
        """Verify SMTP is disabled in test environment."""
        import os

        assert os.environ.get("ENVIRONMENT") == "testing"
        assert os.environ.get("SMTP_HOST") == ""
        assert os.environ.get("SMTP_USER") == ""
        assert os.environ.get("SMTP_PASSWORD") == ""
