"""Supabase data layer.

Every query against the ``public.messages`` table lives here; no other module
talks to Supabase directly (CONTRACT.md §2). The client is created lazily so the
app can be imported (and unit-tested with the DB faked) without valid creds.
"""

from __future__ import annotations

from typing import Any, Optional

from supabase import Client, create_client

from . import config

# Column projection used everywhere a thread is returned to the API.
_THREAD_COLUMNS = (
    "id,conversation_id,conversation_name,role,content,tool_calls,"
    "needs_attention,read,created_at"
)

_client: Optional[Client] = None


def get_client() -> Client:
    """Return a cached Supabase client, creating it on first use."""
    global _client
    if _client is None:
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client


# --- Inserts ----------------------------------------------------------------


def insert_visitor_message(
    conversation_id: str,
    content: str,
    conversation_name: Optional[str] = None,
) -> dict[str, Any]:
    """Persist a visitor turn (role=visitor, read=false)."""
    row: dict[str, Any] = {
        "conversation_id": conversation_id,
        "role": "visitor",
        "content": content,
        "read": False,
        "needs_attention": False,
    }
    if conversation_name:
        row["conversation_name"] = conversation_name
    result = get_client().table("messages").insert(row).execute()
    return result.data[0]


def insert_avatar_message(
    conversation_id: str,
    content: str,
    tool_calls: Optional[list[dict[str, Any]]] = None,
    needs_attention: bool = False,
) -> dict[str, Any]:
    """Persist an avatar turn (role=avatar, read=false)."""
    row: dict[str, Any] = {
        "conversation_id": conversation_id,
        "role": "avatar",
        "content": content,
        "tool_calls": tool_calls if tool_calls else None,
        "needs_attention": needs_attention,
        "read": False,
    }
    result = get_client().table("messages").insert(row).execute()
    return result.data[0]


def insert_human_message(conversation_id: str, content: str) -> dict[str, Any]:
    """Persist an owner (human) turn (role=human, read=true)."""
    row: dict[str, Any] = {
        "conversation_id": conversation_id,
        "role": "human",
        "content": content,
        "read": True,
        "needs_attention": False,
    }
    result = get_client().table("messages").insert(row).execute()
    return result.data[0]


# --- Reads ------------------------------------------------------------------


def get_conversation(conversation_id: str) -> list[dict[str, Any]]:
    """Return all rows for a conversation ordered by created_at ascending.

    Returns an empty list for unknown ids.
    """
    result = (
        get_client()
        .table("messages")
        .select(_THREAD_COLUMNS)
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .order("id", desc=False)
        .execute()
    )
    return result.data or []


def open_conversation(conversation_id: str) -> list[dict[str, Any]]:
    """Open a thread in admin: a single PostgREST update-returning call that
    marks every row ``read=true, needs_attention=false`` and returns the updated
    rows (CONTRACT.md §7). Returns an empty list when the conversation is empty.
    """
    result = (
        get_client()
        .table("messages")
        .update({"read": True, "needs_attention": False})
        .eq("conversation_id", conversation_id)
        .execute()
    )
    rows = result.data or []
    rows.sort(key=lambda r: (r.get("created_at") or "", r.get("id") or 0))
    return rows


def list_all_messages() -> list[dict[str, Any]]:
    """Return every message row (used to aggregate the admin inbox in Python)."""
    result = (
        get_client()
        .table("messages")
        .select(_THREAD_COLUMNS)
        .order("created_at", desc=False)
        .order("id", desc=False)
        .execute()
    )
    return result.data or []
