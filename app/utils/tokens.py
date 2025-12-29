"""Token generation utilities."""

import secrets


def generate_invite_token(length: int = 32) -> str:
    """
    Generate a secure random token for invites.

    Args:
        length: Length of the token in bytes (default: 32)

    Returns:
        URL-safe random token string
    """
    return secrets.token_urlsafe(length)


def generate_reset_token(length: int = 32) -> str:
    """
    Generate a secure random token for password resets.

    Args:
        length: Length of the token in bytes (default: 32)

    Returns:
        URL-safe random token string
    """
    return secrets.token_urlsafe(length)
