"""Tests for ``app.tools`` — the Pushover helper and the function tools.

The ``push()`` helper is tested directly (it is the testable core that
``push_tool`` wraps). We never hit the real Pushover API: ``requests.post`` is
monkeypatched. The decorated function tools are checked for presence and naming
(CONTRACT.md §6).
"""

from __future__ import annotations

import pytest

from app import config, knowledge, tools


class _FakeResp:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_push_noop_when_creds_unset(monkeypatch):
    monkeypatch.setattr(config, "PUSHOVER_USER", None)
    monkeypatch.setattr(config, "PUSHOVER_TOKEN", None)

    called = {"n": 0}

    def _should_not_call(*a, **k):  # pragma: no cover - asserted never called
        called["n"] += 1
        raise AssertionError("requests.post should not be called when unset")

    monkeypatch.setattr(tools.requests, "post", _should_not_call)
    out = tools.push("hello owner")
    assert "not configured" in out.lower() or "not sent" in out.lower()
    assert called["n"] == 0


def test_push_sends_when_configured(monkeypatch):
    monkeypatch.setattr(config, "PUSHOVER_USER", "u123")
    monkeypatch.setattr(config, "PUSHOVER_TOKEN", "t456")

    captured = {}

    def _fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        return _FakeResp(200)

    monkeypatch.setattr(tools.requests, "post", _fake_post)
    out = tools.push("visitor wants to talk")
    assert captured["url"] == tools.PUSHOVER_URL
    assert captured["data"]["user"] == "u123"
    assert captured["data"]["token"] == "t456"
    assert captured["data"]["message"] == "visitor wants to talk"
    assert "200" in out
    assert "sent" in out.lower()


def test_push_handles_network_error(monkeypatch):
    monkeypatch.setattr(config, "PUSHOVER_USER", "u123")
    monkeypatch.setattr(config, "PUSHOVER_TOKEN", "t456")

    def _boom(*a, **k):
        raise tools.requests.RequestException("connection refused")

    monkeypatch.setattr(tools.requests, "post", _boom)
    out = tools.push("anything")
    # Stays graceful — returns a benign string, never raises.
    assert "could not be sent" in out.lower()


def test_function_tools_exist():
    # Both function tools are defined and discoverable; the SDK decorator wraps
    # them as tool objects (we don't invoke them here — that needs the runner).
    assert tools.faq_tool is not None
    assert tools.push_tool is not None


def test_function_tools_named():
    """The decorated tools expose their function name (the SDK derives the tool
    name from it); probe defensively across SDK versions."""

    def _name(obj):
        for attr in ("name", "tool_name", "__name__"):
            value = getattr(obj, attr, None)
            if isinstance(value, str) and value:
                return value
        fn = getattr(obj, "on_invoke_tool", None)
        return getattr(fn, "__name__", "")

    assert "faq_tool" in _name(tools.faq_tool)
    assert "push_tool" in _name(tools.push_tool)


def test_faq_tool_core_matches_knowledge():
    """The faq_tool wraps ``knowledge.faq_tool_answer``; verify that core."""
    first = knowledge.FAQS[0]
    n = int(first["faq"])
    assert knowledge.faq_tool_answer(n) == (
        f"### Question {first['faq']}:\n{first['question']}\n"
        f"### Answer:\n{first['answer']}"
    )
