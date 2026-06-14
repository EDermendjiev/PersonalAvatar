"""Tests for the public, unguarded endpoints (CONTRACT.md §7, §8, §10).

* ``GET /api/config`` → owner name + model,
* ``GET /api/conversation/{id}`` → full thread shape, ordering, name derivation,
  empty (200) for unknown ids,
* static serving falls back to a friendly note when ``dist/`` is absent.

DB is faked in-memory; no network.
"""

from __future__ import annotations

import uuid

import pytest

from app import config, main


def _cid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# /api/config
# ---------------------------------------------------------------------------


def test_config_endpoint(client, monkeypatch):
    monkeypatch.setattr(config, "OWNER_NAME", "Emil Dermendzhiev")
    monkeypatch.setattr(config, "MODEL", "openai/gpt-5.4-mini")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json() == {
        "owner_name": "Emil Dermendzhiev",
        "model": "openai/gpt-5.4-mini",
    }


def test_config_is_public(client):
    # No auth required.
    assert client.get("/api/config").status_code == 200


# ---------------------------------------------------------------------------
# /api/conversation/{id}
# ---------------------------------------------------------------------------


def test_conversation_fetch_shape_and_order(client, fake_db):
    cid = _cid()
    fake_db.insert_visitor_message(cid, "first", "Ann")
    fake_db.insert_avatar_message(cid, "reply", tool_calls=None)
    fake_db.insert_visitor_message(cid, "second")

    resp = client.get(f"/api/conversation/{cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] == cid
    assert body["conversation_name"] == "Ann"  # latest non-null name
    msgs = body["messages"]
    assert [m["role"] for m in msgs] == ["visitor", "avatar", "visitor"]
    assert [m["content"] for m in msgs] == ["first", "reply", "second"]
    # Each message has the contract fields.
    for m in msgs:
        assert set(m.keys()) >= {
            "id",
            "role",
            "content",
            "tool_calls",
            "needs_attention",
            "read",
            "created_at",
        }


def test_conversation_name_latest_non_null_wins(client, fake_db):
    cid = _cid()
    fake_db.insert_visitor_message(cid, "m1", "First Name")
    fake_db.insert_visitor_message(cid, "m2")  # no name
    fake_db.insert_visitor_message(cid, "m3", "Second Name")
    body = client.get(f"/api/conversation/{cid}").json()
    assert body["conversation_name"] == "Second Name"


def test_conversation_unknown_id_returns_empty_200(client, fake_db):
    cid = _cid()
    resp = client.get(f"/api/conversation/{cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] == cid
    assert body["messages"] == []
    assert body["conversation_name"] is None


def test_conversation_only_returns_its_own_rows(client, fake_db):
    a, b = _cid(), _cid()
    fake_db.insert_visitor_message(a, "for A", "A")
    fake_db.insert_visitor_message(b, "for B", "B")
    body = client.get(f"/api/conversation/{a}").json()
    assert len(body["messages"]) == 1
    assert body["messages"][0]["content"] == "for A"


# ---------------------------------------------------------------------------
# Static serving fallback (dist absent in test/dev)
# ---------------------------------------------------------------------------


def test_index_dev_note_when_no_build(client):
    # In the test/dev tree there is no frontend/dist build; the route returns a
    # friendly HTML note rather than crashing.
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    if not main._INDEX.is_file():
        assert "Avatar backend is running" in resp.text


def test_admin_page_served(client):
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_html_entrypoints_are_no_cache_when_built(client):
    # The HTML entry points reference fingerprinted asset filenames; if a browser
    # caches an old index.html, after a redeploy it requests asset hashes that no
    # longer exist and the app breaks until a hard refresh. Serve the HTML with
    # ``no-cache`` so the browser always revalidates it. (Only the FileResponse
    # path sets this; the dev-note fallback has no build to go stale.)
    if main._INDEX.is_file():
        assert client.get("/").headers.get("cache-control") == "no-cache"
    if main._ADMIN.is_file():
        assert client.get("/admin").headers.get("cache-control") == "no-cache"
