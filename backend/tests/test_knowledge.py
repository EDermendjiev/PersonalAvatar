"""Tests for ``app.knowledge`` — knowledge loading, Qn detection, FAQ lookup.

These exercise the real ``knowledge/`` files (loaded at import) so they verify
the actual shipped FAQ as well as the parsing/formatting logic (CONTRACT.md §3,
§6, §7).
"""

from __future__ import annotations

import pytest

from app import knowledge


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_faqs_loaded_and_indexed():
    assert len(knowledge.FAQS) >= 1
    # Every FAQ row has the three required fields.
    for faq in knowledge.FAQS:
        assert {"faq", "question", "answer", "query"} <= set(faq.keys())
    # The number index covers every row.
    assert set(knowledge.FAQ_BY_NUMBER.keys()) == {
        int(f["faq"]) for f in knowledge.FAQS
    }


def test_knowledge_and_style_text_present():
    # The real knowledge files are non-empty markdown.
    assert isinstance(knowledge.KNOWLEDGE_MD, str)
    assert isinstance(knowledge.STYLE_MD, str)
    assert knowledge.KNOWLEDGE_MD.strip()
    assert knowledge.STYLE_MD.strip()


def test_faq_routing_list_lists_every_query():
    routing = knowledge.faq_routing_list()
    for faq in knowledge.FAQS:
        assert f"{faq['faq']}. {faq['query']}" in routing
    # It is newline-prefixed (each entry starts on its own line).
    assert routing.startswith("\n")


# ---------------------------------------------------------------------------
# Qn detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Q1", 1),
        ("Q2", 2),
        ("q2", 2),
        ("  Q12  ", 12),
        ("\tQ3\n", 3),
        ("Q007", 7),
    ],
)
def test_detect_qn_matches(text, expected):
    assert knowledge.detect_qn(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "Q",
        "Question 2",
        "Q2 please",
        "tell me Q2",
        "Q 2",
        "2",
        "QQ2",
        "Q2a",
    ],
)
def test_detect_qn_non_matches(text):
    assert knowledge.detect_qn(text) is None


def test_detect_qn_handles_none():
    assert knowledge.detect_qn(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# FAQ lookup / faq_tool answer
# ---------------------------------------------------------------------------


def test_lookup_faq_found_and_missing():
    first = knowledge.FAQS[0]
    n = int(first["faq"])
    assert knowledge.lookup_faq(n) == first
    assert knowledge.lookup_faq(99999) is None


def test_faq_tool_answer_formats_question_and_answer():
    first = knowledge.FAQS[0]
    n = int(first["faq"])
    out = knowledge.faq_tool_answer(n)
    assert out.startswith(f"### Question {n}:")
    assert first["question"] in out
    assert "### Answer:" in out
    assert first["answer"] in out


def test_faq_tool_answer_not_found():
    out = knowledge.faq_tool_answer(99999)
    assert "no FAQ number 99999" in out
    assert "###" not in out  # not the formatted shape


# ---------------------------------------------------------------------------
# Instant (Qn) answer
# ---------------------------------------------------------------------------


def test_instant_answer_restates_question_then_answer():
    first = knowledge.FAQS[0]
    n = int(first["faq"])
    out = knowledge.instant_answer(n)
    assert out.startswith(f"**Q{n}:** {first['question']}")
    assert out.endswith(first["answer"])
    # blank line between restated question and the answer
    assert "\n\n" in out


def test_instant_answer_not_found_is_friendly():
    out = knowledge.instant_answer(99999)
    assert "Q99999" in out
    assert "don't have" in out.lower()
