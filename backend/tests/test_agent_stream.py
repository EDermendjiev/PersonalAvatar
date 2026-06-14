"""Tests for ``app.agent`` — the SDK-event → typed-tuple mapping.

These never hit the network: ``Runner.run_streamed`` is monkeypatched to return a
fake result whose ``stream_events()`` yields fabricated SDK events. We verify
that ``stream_reply`` maps:
  * a raw ``ResponseTextDeltaEvent`` → ``("delta", text)``,
  * a ``tool_called`` run-item event → ``("tool_called", name, args)``,
  * a ``tool_output`` run-item event → ``("tool_output", name)``,
and that ``build_agent`` wires the OpenRouter model + both tools (CONTRACT.md §4).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app import agent, config


# ---------------------------------------------------------------------------
# Fake SDK event objects
# ---------------------------------------------------------------------------


def _delta_event(text: str):
    """A raw_response_event carrying a ResponseTextDeltaEvent in ``.data``."""
    from openai.types.responses import ResponseTextDeltaEvent

    # Construct defensively: build_args covers the known required fields across
    # SDK versions; extras are ignored by pydantic's constructor here.
    try:
        data = ResponseTextDeltaEvent(
            content_index=0,
            delta=text,
            item_id="item-1",
            output_index=0,
            sequence_number=0,
            type="response.output_text.delta",
            logprobs=[],
        )
    except Exception:
        # Fallback for older/newer field sets — set attributes directly.
        data = ResponseTextDeltaEvent.model_construct(delta=text)
    return SimpleNamespace(type="raw_response_event", data=data)


def _tool_called_event(name: str, args: str | None):
    raw = SimpleNamespace(name=name, arguments=args)
    item = SimpleNamespace(tool_name=name, raw_item=raw)
    return SimpleNamespace(
        type="run_item_stream_event", name="tool_called", item=item
    )


def _tool_output_event(name: str):
    raw = SimpleNamespace(name=name)
    item = SimpleNamespace(tool_name=name, raw_item=raw)
    return SimpleNamespace(
        type="run_item_stream_event", name="tool_output", item=item
    )


def _ignored_event():
    """An event type the mapper should silently skip."""
    return SimpleNamespace(type="agent_updated_stream_event")


class _FakeResult:
    def __init__(self, events):
        self._events = events

    async def stream_events(self):
        for ev in self._events:
            await asyncio.sleep(0)
            yield ev


def _collect(gen) -> list[tuple]:
    """Drain an async generator to a list, synchronously."""

    async def _run():
        out = []
        async for item in gen:
            out.append(item)
        return out

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_stream_reply_maps_deltas(monkeypatch):
    events = [_delta_event("Hello "), _delta_event("world")]
    monkeypatch.setattr(
        agent.Runner, "run_streamed", lambda *a, **k: _FakeResult(events)
    )
    out = _collect(agent.stream_reply("transcript", "instructions"))
    assert out == [("delta", "Hello "), ("delta", "world")]


def test_stream_reply_skips_empty_deltas(monkeypatch):
    events = [_delta_event(""), _delta_event("x")]
    monkeypatch.setattr(
        agent.Runner, "run_streamed", lambda *a, **k: _FakeResult(events)
    )
    out = _collect(agent.stream_reply("t", "i"))
    # Empty delta is dropped.
    assert out == [("delta", "x")]


def test_stream_reply_maps_tool_called_and_output(monkeypatch):
    events = [
        _tool_called_event("faq_tool", '{"question_number": 1}'),
        _tool_output_event("faq_tool"),
        _delta_event("answer"),
    ]
    monkeypatch.setattr(
        agent.Runner, "run_streamed", lambda *a, **k: _FakeResult(events)
    )
    out = _collect(agent.stream_reply("t", "i"))
    assert out[0] == ("tool_called", "faq_tool", '{"question_number": 1}')
    assert out[1] == ("tool_output", "faq_tool")
    assert out[2] == ("delta", "answer")


def test_stream_reply_ignores_unknown_events(monkeypatch):
    events = [_ignored_event(), _delta_event("only this")]
    monkeypatch.setattr(
        agent.Runner, "run_streamed", lambda *a, **k: _FakeResult(events)
    )
    out = _collect(agent.stream_reply("t", "i"))
    assert out == [("delta", "only this")]


def test_push_tool_detectable_in_stream(monkeypatch):
    events = [
        _tool_called_event("push_tool", '{"message": "ping"}'),
        _tool_output_event("push_tool"),
    ]
    monkeypatch.setattr(
        agent.Runner, "run_streamed", lambda *a, **k: _FakeResult(events)
    )
    out = _collect(agent.stream_reply("t", "i"))
    called = [e for e in out if e[0] == "tool_called"]
    assert called and called[0][1] == "push_tool"


def test_build_agent_wires_model_and_tools(monkeypatch):
    # Avoid building a real network client.
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(config, "MODEL", "openai/gpt-5.4-nano")
    a = agent.build_agent("system instructions")
    assert a.name == "Avatar"
    assert a.instructions == "system instructions"
    # Both function tools are attached.
    assert len(a.tools) == 2


def test_tool_name_from_item_probes_attributes():
    # Direct unit test of the defensive name extractor.
    item1 = SimpleNamespace(tool_name="faq_tool")
    item2 = SimpleNamespace(name="push_tool")
    item3 = SimpleNamespace(raw_item=SimpleNamespace(name="faq_tool"))
    item4 = SimpleNamespace(raw_item=SimpleNamespace(nothing=True))
    assert agent._tool_name_from_item(item1) == "faq_tool"
    assert agent._tool_name_from_item(item2) == "push_tool"
    assert agent._tool_name_from_item(item3) == "faq_tool"
    assert agent._tool_name_from_item(item4) is None
