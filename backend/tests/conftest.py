"""Shared pytest fixtures and fakes for the Avatar backend tests.

Everything here is designed so the whole suite runs with **no network**: the
Supabase data layer is replaced by an in-memory ``FakeDB`` and the agent's
streaming reply is replaced by a fake async generator. The only tests that touch
the real model are explicitly marked ``@pytest.mark.llm`` (none are by default).

Design notes
------------
* ``app.main`` calls the data layer as ``db.<func>`` and the agent as
  ``agent.stream_reply`` (module-attribute access), so monkeypatching the
  attributes on the ``app.db`` / ``app.agent`` modules is sufficient — the route
  code resolves the name at call time.
* The rate limiter keeps in-process state; ``reset_ratelimit`` (autouse) clears
  it before every test so order never matters.
* ``ADMIN_PASSWORD`` is forced to a known value per-test so the auth tests never
  depend on the real ``.env`` secret. The session serializer is built from
  ``SESSION_SECRET`` at import time and is reused for sign + verify, so a login
  with the patched password yields a cookie that ``require_admin`` accepts.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Callable, Optional

import pytest
from fastapi.testclient import TestClient

from app import agent, config, db, main, ratelimit

ADMIN_PASSWORD = "test-admin-pw"


# ---------------------------------------------------------------------------
# In-memory fake of the Supabase data layer (app/db.py)
# ---------------------------------------------------------------------------


class FakeDB:
    """A faithful in-memory stand-in for ``app.db``.

    It mirrors the public functions of the real data layer and the *insert
    rules* and *read shapes* in CONTRACT.md §2/§7: visitor/avatar rows default
    ``read=false``; human rows are ``read=true, needs_attention=false``;
    ``open_conversation`` marks every row in the thread ``read=true,
    needs_attention=false`` and returns them; ``get_conversation`` /
    ``list_all_messages`` return rows ordered by ``(created_at, id)``.
    """

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._next_id = 1
        # Counters/flags so tests can assert behaviour precisely.
        self.open_calls: list[str] = []

    # -- internal helpers --
    def _add(self, row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row["id"] = self._next_id
        self._next_id += 1
        # A deterministic, monotonically increasing ISO-ish timestamp so order
        # is stable without depending on wall-clock resolution.
        row.setdefault(
            "created_at", f"2026-01-01T00:00:{row['id'] - 1:02d}+00:00"
        )
        row.setdefault("conversation_name", None)
        row.setdefault("tool_calls", None)
        row.setdefault("needs_attention", False)
        row.setdefault("read", False)
        self.rows.append(row)
        return dict(row)

    def _sorted(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            rows, key=lambda r: (r.get("created_at") or "", r.get("id") or 0)
        )

    # -- inserts --
    def insert_visitor_message(
        self,
        conversation_id: str,
        content: str,
        conversation_name: Optional[str] = None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "conversation_id": conversation_id,
            "role": "visitor",
            "content": content,
            "read": False,
            "needs_attention": False,
        }
        if conversation_name:
            row["conversation_name"] = conversation_name
        return self._add(row)

    def insert_avatar_message(
        self,
        conversation_id: str,
        content: str,
        tool_calls: Optional[list[dict[str, Any]]] = None,
        needs_attention: bool = False,
    ) -> dict[str, Any]:
        return self._add(
            {
                "conversation_id": conversation_id,
                "role": "avatar",
                "content": content,
                "tool_calls": tool_calls if tool_calls else None,
                "needs_attention": needs_attention,
                "read": False,
            }
        )

    def insert_human_message(
        self, conversation_id: str, content: str
    ) -> dict[str, Any]:
        return self._add(
            {
                "conversation_id": conversation_id,
                "role": "human",
                "content": content,
                "read": True,
                "needs_attention": False,
            }
        )

    # -- reads --
    def get_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = [
            dict(r)
            for r in self.rows
            if r["conversation_id"] == conversation_id
        ]
        return self._sorted(rows)

    def open_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        self.open_calls.append(conversation_id)
        touched: list[dict[str, Any]] = []
        for r in self.rows:
            if r["conversation_id"] == conversation_id:
                r["read"] = True
                r["needs_attention"] = False
                touched.append(dict(r))
        return self._sorted(touched)

    def list_all_messages(self) -> list[dict[str, Any]]:
        return self._sorted([dict(r) for r in self.rows])


# ---------------------------------------------------------------------------
# Fake agent streaming (app/agent.py:stream_reply)
# ---------------------------------------------------------------------------


def make_fake_stream(
    events: list[tuple],
) -> Callable[..., AsyncGenerator[tuple, None]]:
    """Return a drop-in replacement for ``agent.stream_reply`` that yields the
    given list of typed tuples (``("delta", str)`` / ``("tool_called", name,
    args)`` / ``("tool_output", name)``)."""

    async def _fake(transcript: str, instructions: str):
        # touch args so a wrong signature surfaces as a test failure
        assert isinstance(transcript, str)
        assert isinstance(instructions, str)
        for ev in events:
            await asyncio.sleep(0)
            yield ev

    return _fake


def make_raising_stream(
    exc: Exception, before: Optional[list[tuple]] = None
):
    """A fake ``stream_reply`` that yields ``before`` (if any) then raises."""

    async def _fake(transcript: str, instructions: str):
        for ev in before or []:
            await asyncio.sleep(0)
            yield ev
        raise exc
        yield  # pragma: no cover - keeps this an async generator

    return _fake


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_ratelimit():
    """Clear in-process rate-limit state before and after every test."""
    ratelimit.reset()
    yield
    ratelimit.reset()


@pytest.fixture
def fake_db(monkeypatch) -> FakeDB:
    """Replace every data-layer function used by the app with the in-memory fake.

    Patches the bound functions on the ``app.db`` module so that ``main.py``'s
    ``db.<func>`` lookups resolve to the fake.
    """
    fake = FakeDB()
    for name in (
        "insert_visitor_message",
        "insert_avatar_message",
        "insert_human_message",
        "get_conversation",
        "open_conversation",
        "list_all_messages",
    ):
        monkeypatch.setattr(db, name, getattr(fake, name))
    return fake


@pytest.fixture
def patch_password(monkeypatch):
    """Force a known admin password for the auth tests."""
    monkeypatch.setattr(config, "ADMIN_PASSWORD", ADMIN_PASSWORD)
    # main.py reads config.ADMIN_PASSWORD via the module, so patching the
    # attribute is enough for the login route.
    return ADMIN_PASSWORD


@pytest.fixture
def client(fake_db) -> TestClient:
    """An anonymous TestClient with the DB faked (no network)."""
    return TestClient(main.app)


@pytest.fixture
def admin_client(fake_db, patch_password) -> TestClient:
    """A TestClient that has logged in as admin (session cookie set)."""
    c = TestClient(main.app)
    resp = c.post("/api/admin/login", json={"password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    return c


@pytest.fixture
def set_agent_stream(monkeypatch):
    """Helper to install a fake ``agent.stream_reply`` for a test.

    Usage: ``set_agent_stream(make_fake_stream([...]))``.
    """

    def _install(fake_callable) -> None:
        monkeypatch.setattr(agent, "stream_reply", fake_callable)

    return _install
