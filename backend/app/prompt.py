"""Prompt composition for the 3-way conversation.

Builds the system instructions and the single user-prompt transcript that
summarizes the whole conversation (visitor <-> Avatar <-> human owner). Because
the human role cannot be expressed as plain user/assistant turns, the entire
history is flattened into one user prompt each turn (SPEC + CONTRACT.md §5).
"""

from __future__ import annotations

from typing import Any

from . import config, knowledge


def build_instructions() -> str:
    """Compose the system prompt in the order defined by CONTRACT.md §5."""
    owner = config.OWNER_NAME

    role = (
        f"You are the digital twin (an AI) of {owner}, chatting with visitors on "
        f"{owner}'s website. You represent {owner}; answer about their career, "
        "background, skills, work and services in the first person as the twin. "
        f"If asked, say clearly you are an AI digital twin of {owner}."
    )

    three_way = (
        f"This is a three-way conversation. {owner} (the real human) may "
        "personally join at any time; their messages are labelled as the "
        "human/owner and are the real person speaking. Treat those messages as "
        "authoritative context. Do NOT impersonate, repeat, or contradict the "
        f"human's messages, and never reply on {owner}'s behalf. You are the "
        "Avatar, a distinct AI participant."
    )

    who_i_am = f"# Who I am\n\n{knowledge.KNOWLEDGE_MD}"

    voice = f"# Voice and rules\n\n{knowledge.STYLE_MD}"

    faq_routing = (
        "# FAQ routing\n\n"
        "Your `faq_tool` returns full answers to common questions by number. If "
        "the visitor's question matches one of the questions below, call "
        "`faq_tool` with that number and answer in the original markdown. The "
        "questions, by number:" + knowledge.faq_routing_list()
    )

    tools_contact = (
        "# Tools and contact\n\n"
        "Use `faq_tool` for known questions. If the visitor wants to get in "
        "touch, ask for their email first, then call `push_tool` to notify "
        f"{owner}. If you cannot answer a question or it genuinely needs the "
        "human, call `push_tool` to notify the owner AND tell the visitor you've "
        "done so. Never invent information."
    )

    formatting = (
        "# Formatting\n\n"
        "Respond in markdown with no code blocks. Always write links as "
        "clickable markdown, never bare URLs. Defer to the voice and rules above "
        "for tone, length, and safety."
    )

    sections = [
        role,
        three_way,
        who_i_am,
        voice,
        faq_routing,
        tools_contact,
        formatting,
    ]
    return "\n\n".join(sections).strip()


def _format_role_line(row: dict[str, Any]) -> str:
    """Render one prior message as a role-prefixed transcript line."""
    role = row.get("role")
    content = row.get("content", "")
    if role == "visitor":
        name = (row.get("conversation_name") or "").strip()
        prefix = f"Visitor ({name})" if name else "Visitor"
        return f"{prefix}: {content}"
    if role == "avatar":
        return f"You (the Avatar): {content}"
    if role == "human":
        return f"{config.OWNER_NAME} (the human, joined live): {content}"
    # Unknown role: render defensively rather than dropping it.
    return f"{role}: {content}"


def build_transcript(
    messages: list[dict[str, Any]],
    latest_visitor_message: str,
    visitor_name: str | None = None,
) -> str:
    """Build the single user prompt: a readable, role-labelled transcript of all
    prior messages followed by the latest visitor line and a trailing
    instruction (CONTRACT.md §5).

    ``messages`` should be the full prior thread (already persisted, including
    the just-stored latest visitor message). If the latest visitor message is
    not already the final row, it is appended so the model always sees it last.
    """
    lines: list[str] = [_format_role_line(row) for row in messages]

    # Ensure the latest visitor message is present as the final visitor line.
    latest = (latest_visitor_message or "").strip()
    already_last = (
        messages
        and messages[-1].get("role") == "visitor"
        and (messages[-1].get("content") or "").strip() == latest
    )
    if latest and not already_last:
        name = (visitor_name or "").strip()
        prefix = f"Visitor ({name})" if name else "Visitor"
        lines.append(f"{prefix}: {latest_visitor_message}")

    transcript = "\n".join(lines)
    return (
        f"{transcript}\n\nRespond as the Avatar to the latest visitor message."
    ).strip()
