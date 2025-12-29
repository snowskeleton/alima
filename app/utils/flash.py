"""Flash message utilities for displaying user feedback."""

from typing import List, Literal
from fastapi import Request

MessageType = Literal["success", "error", "info", "warning"]


def flash(request: Request, message: str, category: MessageType = "info") -> None:
    """
    Add a flash message to the session.

    Args:
        request: FastAPI request object
        message: Message text to display
        category: Message type (success, error, info, warning)
    """
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({"text": message, "category": category})


def get_flashed_messages(request: Request) -> List[dict]:
    """
    Get and clear all flash messages from the session.

    Args:
        request: FastAPI request object

    Returns:
        List of message dictionaries with 'text' and 'category' keys
    """
    messages = request.session.pop("_messages", [])
    return messages
