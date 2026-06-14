"""Agent tools: FAQ lookup and Pushover notification.

These are the ``@function_tool``s the Agent is given. ``push()`` is a plain
helper (testable without the SDK) and ``push_tool`` wraps it. Pushover is
optional: when creds are unset the push tool returns a benign string and never
raises (CONTRACT.md §6).
"""

from __future__ import annotations

import requests
from agents import function_tool

from . import config, knowledge

PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


def push(message: str) -> str:
    """Send a Pushover notification to the owner. No-ops gracefully when creds
    are missing and swallows network errors so a tool call never crashes a turn.
    """
    if not config.PUSHOVER_USER or not config.PUSHOVER_TOKEN:
        return (
            "Notification not sent: Pushover is not configured on this "
            "deployment. The owner will not receive a push for this message."
        )
    payload = {
        "user": config.PUSHOVER_USER,
        "token": config.PUSHOVER_TOKEN,
        "message": message,
    }
    try:
        status = requests.post(PUSHOVER_URL, data=payload, timeout=10).status_code
    except requests.RequestException as exc:  # network/timeout: stay graceful
        return f"Notification could not be sent (network error: {exc})."
    return f"Notification sent to the owner (status {status})."


@function_tool
def faq_tool(question_number: int) -> str:
    """Retrieve the full answer to a frequently asked question by its number.

    Args:
        question_number: The FAQ number to retrieve (from the routing list in
            your instructions).
    """
    return knowledge.faq_tool_answer(question_number)


@function_tool
def push_tool(message: str) -> str:
    """Notify the human owner via a Pushover push notification.

    Use this when the visitor wants to get in touch (after collecting their
    email) or when a question needs the human or cannot be answered.

    Args:
        message: The message to send to the human owner.
    """
    return push(message)
