"""Tiny SSE parser shared by the chat tests.

The chat endpoint emits one ``data: <json>\\n\\n`` frame per event (CONTRACT.md
§7). ``parse_sse`` turns the raw response text into the list of decoded JSON
event dicts so tests can assert on event ``type`` and payloads.
"""

from __future__ import annotations

import json
from typing import Any


def parse_sse(text: str) -> list[dict[str, Any]]:
    """Decode SSE ``data:`` frames from a response body into JSON event dicts."""
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                payload = line[len("data:") :].strip()
                if payload:
                    events.append(json.loads(payload))
    return events


def events_of_type(events: list[dict[str, Any]], type_: str) -> list[dict[str, Any]]:
    """Filter decoded events by their ``type`` field."""
    return [e for e in events if e.get("type") == type_]
