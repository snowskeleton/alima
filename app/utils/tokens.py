"""Token generation utilities."""

import secrets


def generate_invite_token(length: int = 32) -> str:
    """Generate a secure random token for invites."""
    return secrets.token_urlsafe(length)


def generate_magic_link_token(length: int = 32) -> str:
    """Generate a secure random token for magic links."""
    return secrets.token_urlsafe(length)
