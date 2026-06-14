"""Tests for ``app.prompt`` — system instructions + the single-user transcript.

Verifies the instruction sections (role, three-way context, knowledge, style,
FAQ routing, tools/contact) and the role-labelled transcript including the human
(owner) role, all driven by ``OWNER_NAME`` from config (CONTRACT.md §5).
"""

from __future__ import annotations

import pytest

from app import config, knowledge, prompt


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(config, "OWNER_NAME", "Emil Dermendzhiev")
    return "Emil Dermendzhiev"


# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------


def test_instructions_contain_role_and_owner(owner):
    instr = prompt.build_instructions()
    assert "digital twin" in instr.lower()
    assert owner in instr
    assert "AI digital twin" in instr


def test_instructions_explain_three_way_human(owner):
    instr = prompt.build_instructions()
    lowered = instr.lower()
    assert "three-way" in lowered
    # Must instruct the avatar not to impersonate / reply for the human.
    assert "impersonate" in lowered
    assert "authoritative" in lowered


def test_instructions_embed_knowledge_and_style(owner):
    instr = prompt.build_instructions()
    assert knowledge.KNOWLEDGE_MD.strip() in instr
    assert knowledge.STYLE_MD.strip() in instr


def test_instructions_include_faq_routing_and_tools(owner):
    instr = prompt.build_instructions()
    assert "faq_tool" in instr
    assert "push_tool" in instr
    # The numbered routing list is embedded.
    for faq in knowledge.FAQS:
        assert f"{faq['faq']}. {faq['query']}" in instr
    # Contact behaviour: ask for email, then push.
    assert "email" in instr.lower()
    # No-invention safety rule.
    assert "never invent" in instr.lower()


def test_instructions_formatting_section(owner):
    instr = prompt.build_instructions()
    assert "markdown" in instr.lower()


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


def test_transcript_labels_roles(owner):
    messages = [
        {"role": "visitor", "content": "Hi", "conversation_name": "Sam"},
        {"role": "avatar", "content": "Hello there"},
        {"role": "human", "content": "I'm here now"},
    ]
    out = prompt.build_transcript(messages, latest_visitor_message="Hi")
    assert "Visitor (Sam): Hi" in out
    assert "You (the Avatar): Hello there" in out
    assert f"{owner} (the human, joined live): I'm here now" in out
    assert out.rstrip().endswith(
        "Respond as the Avatar to the latest visitor message."
    )


def test_transcript_visitor_without_name(owner):
    messages = [{"role": "visitor", "content": "anon question"}]
    out = prompt.build_transcript(messages, latest_visitor_message="anon question")
    assert "Visitor: anon question" in out
    assert "Visitor (" not in out


def test_transcript_appends_latest_when_not_last(owner):
    """If the latest visitor message isn't the final row, it is appended last so
    the model always sees it last."""
    messages = [
        {"role": "visitor", "content": "old", "conversation_name": "Ann"},
        {"role": "avatar", "content": "an answer"},
    ]
    out = prompt.build_transcript(
        messages, latest_visitor_message="new question", visitor_name="Ann"
    )
    lines = out.splitlines()
    # The appended visitor line precedes the trailing instruction.
    assert "Visitor (Ann): new question" in out
    # And it appears after the avatar line.
    assert out.index("an answer") < out.index("new question")


def test_transcript_does_not_duplicate_latest_when_already_last(owner):
    messages = [
        {"role": "visitor", "content": "only message"},
    ]
    out = prompt.build_transcript(
        messages, latest_visitor_message="only message"
    )
    assert out.count("only message") == 1


def test_transcript_empty_history_with_latest(owner):
    out = prompt.build_transcript([], latest_visitor_message="first ever")
    assert "Visitor: first ever" in out
    assert "Respond as the Avatar" in out


def test_transcript_unknown_role_rendered_defensively(owner):
    messages = [{"role": "system-note", "content": "weird"}]
    out = prompt.build_transcript(messages, latest_visitor_message="hi")
    assert "system-note: weird" in out
