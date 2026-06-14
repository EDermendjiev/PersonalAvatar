"""The Avatar agent and its streaming reply.

Wires the OpenAI Agents SDK to OpenRouter idiomatically (CONTRACT.md §4): an
``AsyncOpenAI`` client pointed at OpenRouter, wrapped in an
``OpenAIChatCompletionsModel``, with tracing disabled. ``stream_reply`` is an
async generator yielding typed tuples that the route layer maps to SSE events.

No direct OpenAI calls and no SQLite session: we rebuild the transcript ourselves
each turn and pass it as a single user prompt (CONTRACT.md §5).
"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from agents import (
    Agent,
    ModelSettings,
    OpenAIChatCompletionsModel,
    Runner,
    set_tracing_disabled,
)
from openai import AsyncOpenAI
from openai.types.responses import ResponseTextDeltaEvent

from . import config
from .tools import faq_tool, push_tool

# OpenRouter has no OpenAI tracing endpoint; disable tracing globally.
set_tracing_disabled(True)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Lazily build the OpenRouter-backed AsyncOpenAI client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
        )
    return _client


def build_agent(instructions: str) -> Agent:
    """Construct an Avatar agent bound to the OpenRouter model and the tools."""
    model = OpenAIChatCompletionsModel(
        model=config.MODEL,
        openai_client=_get_client(),
    )
    return Agent(
        name="Avatar",
        instructions=instructions,
        model=model,
        model_settings=ModelSettings(max_tokens=config.MAX_OUTPUT_TOKENS),
        tools=[faq_tool, push_tool],
    )


def _tool_name_from_item(item: object) -> Optional[str]:
    """Best-effort extraction of a tool name from a run-item stream event item.

    The Agents SDK exposes the tool name in slightly different shapes across
    item types/versions; probe the common attributes defensively.
    """
    for attr in ("tool_name", "name"):
        value = getattr(item, attr, None)
        if isinstance(value, str) and value:
            return value
    raw = getattr(item, "raw_item", None)
    if raw is not None:
        for attr in ("name", "tool_name"):
            value = getattr(raw, attr, None)
            if isinstance(value, str) and value:
                return value
    return None


async def stream_reply(
    transcript: str,
    instructions: str,
) -> AsyncGenerator[tuple, None]:
    """Stream the Avatar's reply for one turn.

    Yields typed tuples the route layer turns into SSE frames:
      * ("delta", <text chunk>)
      * ("tool_called", <tool name>, <args-or-None>)
      * ("tool_output", <tool name-or-None>)

    The caller accumulates text and tool calls itself; this generator only maps
    SDK stream events to the tuple protocol (CONTRACT.md §4).
    """
    agent = build_agent(instructions)
    result = Runner.run_streamed(agent, input=transcript)

    async for ev in result.stream_events():
        if ev.type == "raw_response_event" and isinstance(
            ev.data, ResponseTextDeltaEvent
        ):
            delta = ev.data.delta
            if delta:
                yield ("delta", delta)
        elif ev.type == "run_item_stream_event":
            if ev.name == "tool_called":
                item = getattr(ev, "item", None)
                name = _tool_name_from_item(item)
                args = None
                raw = getattr(item, "raw_item", None)
                if raw is not None:
                    args = getattr(raw, "arguments", None)
                yield ("tool_called", name, args)
            elif ev.name == "tool_output":
                item = getattr(ev, "item", None)
                name = _tool_name_from_item(item)
                yield ("tool_output", name)
