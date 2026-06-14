"""Knowledge loading and FAQ helpers.

Loads the owner profile (``knowledge.md``), voice/style rules (``style.md``) and
the numbered FAQ (``faq.jsonl``) from ``KNOWLEDGE_DIR``. Provides the FAQ lookup
used by ``faq_tool`` and the ``Qn`` instant-answer shortcut, plus the ``Qn``
detection regex (CONTRACT.md §3, §7).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from . import config

# Matches a bare "Qn" instant-answer shortcut (e.g. "Q2", " q12 ").
QN_PATTERN = re.compile(r"^\s*[Qq](\d+)\s*$")


def _read_text(path: Path) -> str:
    """Read a UTF-8 text file, returning empty string when it is missing."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _load_faqs(path: Path) -> list[dict[str, Any]]:
    """Parse the JSONL FAQ file into a list of dicts (skips blank lines)."""
    faqs: list[dict[str, Any]] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return faqs
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        faqs.append(json.loads(line))
    return faqs


# --- Module-level loaded knowledge (loaded once at import) -------------------
KNOWLEDGE_MD: str = _read_text(config.KNOWLEDGE_DIR / "knowledge.md")
STYLE_MD: str = _read_text(config.KNOWLEDGE_DIR / "style.md")
FAQS: list[dict[str, Any]] = _load_faqs(config.KNOWLEDGE_DIR / "faq.jsonl")

# Index FAQs by their number for O(1) lookup.
FAQ_BY_NUMBER: dict[int, dict[str, Any]] = {int(f["faq"]): f for f in FAQS}


def faq_routing_list() -> str:
    """A newline-prefixed numbered list of the concise FAQ ``query`` phrasings,
    used in the system prompt so the model can route a question to a number
    (CONTRACT.md §5 step 5).
    """
    lines = [f"\n{f['faq']}. {f['query']}" for f in FAQS]
    return "".join(lines)


def lookup_faq(question_number: int) -> Optional[dict[str, Any]]:
    """Return the full FAQ dict for a number, or ``None`` if not found."""
    return FAQ_BY_NUMBER.get(question_number)


def faq_tool_answer(question_number: int) -> str:
    """The string ``faq_tool`` returns: the full original question and answer in
    markdown, or a friendly not-found note (CONTRACT.md §6).
    """
    faq = lookup_faq(question_number)
    if faq is None:
        return (
            f"There is no FAQ number {question_number}. Answer from what you "
            "know, or let the visitor know you don't have that on file."
        )
    return (
        f"### Question {faq['faq']}:\n{faq['question']}\n"
        f"### Answer:\n{faq['answer']}"
    )


def detect_qn(message: str) -> Optional[int]:
    """Return the FAQ number if ``message`` is a bare ``Qn`` shortcut, else None."""
    match = QN_PATTERN.match(message or "")
    if not match:
        return None
    return int(match.group(1))


def instant_answer(question_number: int) -> str:
    """The reply for the ``Qn`` instant-answer path: restate the question, then
    the answer (CONTRACT.md §7 step 4). Friendly not-found when unknown.
    """
    faq = lookup_faq(question_number)
    if faq is None:
        return (
            f"I don't have a question **Q{question_number}** on file. Try asking "
            "in your own words and I'll do my best to help."
        )
    return f"**Q{faq['faq']}:** {faq['question']}\n\n{faq['answer']}"
