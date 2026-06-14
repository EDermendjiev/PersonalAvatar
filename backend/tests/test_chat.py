"""Tests for ``POST /api/chat`` — the public SSE chat endpoint.

Covers (CONTRACT.md §7):
* rate-limit returns 429 *before* any LLM call or DB write,
* truncation of over-long messages (what is stored AND streamed),
* the ``Qn`` instant-answer path (2 rows persisted, LLM skipped),
* the LLM happy path with a faked agent stream (delta/tool/done framing),
* ``push_tool`` firing → ``needs_attention=true`` on the persisted avatar row,
* a mid-stream error surfacing as a clean SSE ``error`` event.

All of it runs with the DB faked and the agent stream faked — no network.
"""

from __future__ import annotations

import uuid

import pytest

from app import agent, config, ratelimit
from tests.conftest import make_fake_stream, make_raising_stream
from tests.sse_util import events_of_type, parse_sse


def _cid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Rate limiting (happens first, before LLM and DB)
# ---------------------------------------------------------------------------


def test_rate_limit_returns_429_after_limit(client, fake_db, set_agent_stream):
    cid = _cid()

    # The agent must never be called on the rate-limited request.
    def _never(*a, **k):  # pragma: no cover - asserted via call count
        raise AssertionError("LLM must not be called when rate limited")

    # Exhaust the window directly via the limiter, then a chat must 429.
    for _ in range(config.RATE_LIMIT_PER_MINUTE):
        assert ratelimit.allow(cid) is True

    set_agent_stream(_never)
    resp = client.post(
        "/api/chat", json={"conversation_id": cid, "message": "hello"}
    )
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"] == "rate_limited"
    assert "too quickly" in body["detail"].lower()


def test_rate_limit_429_does_not_write_db(client, fake_db):
    cid = _cid()
    for _ in range(config.RATE_LIMIT_PER_MINUTE):
        assert ratelimit.allow(cid) is True
    resp = client.post(
        "/api/chat", json={"conversation_id": cid, "message": "blocked"}
    )
    assert resp.status_code == 429
    # No visitor row was persisted (limit check precedes the DB write).
    assert fake_db.rows == []


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


def test_long_message_truncated_before_store_and_stream(
    client, fake_db, set_agent_stream
):
    cid = _cid()
    # Capture the transcript the agent receives so we can assert truncation.
    seen = {}

    async def _capture(transcript: str, instructions: str):
        seen["transcript"] = transcript
        yield ("delta", "ok")

    set_agent_stream(_capture)

    long_msg = "x" * (config.MAX_MESSAGE_CHARS + 500)
    resp = client.post(
        "/api/chat", json={"conversation_id": cid, "message": long_msg}
    )
    assert resp.status_code == 200

    # Stored visitor row is the truncated text + note.
    visitor = [r for r in fake_db.rows if r["role"] == "visitor"][0]
    assert len(visitor["content"]) == config.MAX_MESSAGE_CHARS + len(
        config.TRUNCATION_NOTE
    )
    assert visitor["content"].endswith(config.TRUNCATION_NOTE)
    # The transcript sent to the LLM contains the truncation note too.
    assert config.TRUNCATION_NOTE.strip() in seen["transcript"]


def test_short_message_not_truncated(client, fake_db, set_agent_stream):
    cid = _cid()
    set_agent_stream(make_fake_stream([("delta", "hi")]))
    resp = client.post(
        "/api/chat", json={"conversation_id": cid, "message": "short"}
    )
    assert resp.status_code == 200
    visitor = [r for r in fake_db.rows if r["role"] == "visitor"][0]
    assert visitor["content"] == "short"


# ---------------------------------------------------------------------------
# Qn instant-answer path (no LLM)
# ---------------------------------------------------------------------------


def test_qn_instant_answer_skips_llm_and_writes_two_rows(
    client, fake_db, set_agent_stream
):
    cid = _cid()

    def _never(*a, **k):  # pragma: no cover
        raise AssertionError("Qn instant path must not call the LLM")

    set_agent_stream(_never)
    resp = client.post(
        "/api/chat", json={"conversation_id": cid, "message": "Q1"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    # Two rows: the visitor Q1 and the avatar instant answer.
    assert len(fake_db.rows) == 2
    roles = [r["role"] for r in fake_db.rows]
    assert roles == ["visitor", "avatar"]
    avatar = fake_db.rows[1]
    assert avatar["tool_calls"] is None
    assert avatar["needs_attention"] is False
    assert avatar["content"].startswith("**Q1:**")

    # SSE: meta -> delta -> done, with the delta carrying the full instant text.
    events = parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["meta", "delta", "done"]
    assert events[1]["text"].startswith("**Q1:**")
    assert events[2]["needs_attention"] is False
    assert events[2]["tool_calls"] is None


def test_qn_unknown_number_is_friendly(client, fake_db, set_agent_stream):
    cid = _cid()
    set_agent_stream(make_fake_stream([]))  # must not be used
    resp = client.post(
        "/api/chat", json={"conversation_id": cid, "message": "Q9999"}
    )
    assert resp.status_code == 200
    avatar = [r for r in fake_db.rows if r["role"] == "avatar"][0]
    assert "Q9999" in avatar["content"]
    assert "don't have" in avatar["content"].lower()


# ---------------------------------------------------------------------------
# LLM happy path
# ---------------------------------------------------------------------------


def test_llm_happy_path_streams_and_persists(client, fake_db, set_agent_stream):
    cid = _cid()
    set_agent_stream(
        make_fake_stream(
            [("delta", "Hello "), ("delta", "world"), ("delta", "!")]
        )
    )
    resp = client.post(
        "/api/chat",
        json={
            "conversation_id": cid,
            "message": "hi there",
            "visitor_name": "Sam",
        },
    )
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert types[-1] == "done"
    deltas = "".join(e["text"] for e in events_of_type(events, "delta"))
    assert deltas == "Hello world!"

    # Persisted avatar row carries the accumulated full text.
    avatar = [r for r in fake_db.rows if r["role"] == "avatar"][0]
    assert avatar["content"] == "Hello world!"
    assert avatar["needs_attention"] is False
    assert avatar["tool_calls"] is None

    # The visitor name was stored on the visitor row.
    visitor = [r for r in fake_db.rows if r["role"] == "visitor"][0]
    assert visitor["conversation_name"] == "Sam"

    # done carries the new message id + created_at from the persisted row.
    done = events_of_type(events, "done")[0]
    assert done["message_id"] == avatar["id"]
    assert done["created_at"] == avatar["created_at"]


def test_meta_event_carries_conversation_id(client, fake_db, set_agent_stream):
    cid = _cid()
    set_agent_stream(make_fake_stream([("delta", "ok")]))
    resp = client.post(
        "/api/chat", json={"conversation_id": cid, "message": "hi"}
    )
    meta = events_of_type(parse_sse(resp.text), "meta")[0]
    assert meta["conversation_id"] == cid


# ---------------------------------------------------------------------------
# Tool events + needs_attention
# ---------------------------------------------------------------------------


def test_faq_tool_event_streamed(client, fake_db, set_agent_stream):
    cid = _cid()
    set_agent_stream(
        make_fake_stream(
            [
                ("tool_called", "faq_tool", '{"question_number": 1}'),
                ("tool_output", "faq_tool"),
                ("delta", "Here is the answer."),
            ]
        )
    )
    resp = client.post(
        "/api/chat", json={"conversation_id": cid, "message": "what do you do"}
    )
    events = parse_sse(resp.text)
    tool_events = events_of_type(events, "tool")
    phases = [(e["tool"], e["phase"]) for e in tool_events]
    assert ("faq_tool", "called") in phases
    assert ("faq_tool", "output") in phases
    # tool_calls recorded on the persisted avatar row, but not needs_attention.
    avatar = [r for r in fake_db.rows if r["role"] == "avatar"][0]
    assert avatar["needs_attention"] is False
    assert avatar["tool_calls"] and avatar["tool_calls"][0]["tool"] == "faq_tool"


def test_push_tool_sets_needs_attention(client, fake_db, set_agent_stream):
    cid = _cid()
    set_agent_stream(
        make_fake_stream(
            [
                ("tool_called", "push_tool", '{"message": "visitor wants contact"}'),
                ("tool_output", "push_tool"),
                ("delta", "I've let the owner know."),
            ]
        )
    )
    resp = client.post(
        "/api/chat",
        json={"conversation_id": cid, "message": "please contact me"},
    )
    events = parse_sse(resp.text)
    done = events_of_type(events, "done")[0]
    assert done["needs_attention"] is True

    avatar = [r for r in fake_db.rows if r["role"] == "avatar"][0]
    assert avatar["needs_attention"] is True
    assert any(t["tool"] == "push_tool" for t in avatar["tool_calls"])


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_mid_stream_error_emits_error_event(client, fake_db, set_agent_stream):
    cid = _cid()
    set_agent_stream(
        make_raising_stream(
            RuntimeError("model exploded"), before=[("delta", "partial")]
        )
    )
    resp = client.post(
        "/api/chat", json={"conversation_id": cid, "message": "trigger error"}
    )
    # The HTTP response itself is 200 (stream started); the error is in-band.
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    err = events_of_type(events, "error")
    assert err and "model exploded" in err[0]["detail"]
    # No avatar row is persisted when the stream errors out.
    assert not [r for r in fake_db.rows if r["role"] == "avatar"]
    # There must be no 'done' event after an error.
    assert not events_of_type(events, "done")


# ---------------------------------------------------------------------------
# SSE headers
# ---------------------------------------------------------------------------


def test_sse_headers_present(client, fake_db, set_agent_stream):
    cid = _cid()
    set_agent_stream(make_fake_stream([("delta", "x")]))
    resp = client.post(
        "/api/chat", json={"conversation_id": cid, "message": "hi"}
    )
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers.get("cache-control") == "no-cache"
    assert resp.headers.get("x-accel-buffering") == "no"
