"""FastAPI application: API routes + static frontend serving.

Entry point ``app.main:app``. API routers are registered before the static
mount so ``/api/*`` always wins. The built frontend (``frontend/dist``) is
served at ``/`` and ``/admin``; absence of the build is handled gracefully
(CONTRACT.md §6, §7, §8, §10).
"""

from __future__ import annotations

import json
import mimetypes
from typing import Any, AsyncGenerator, Optional

# Register correct MIME types for the built static assets. Some platforms
# (notably Windows, via the registry) map ``.js`` to ``text/plain``, which makes
# browsers refuse ES module scripts ("Strict MIME type checking"). Registering
# these explicitly keeps StaticFiles correct everywhere.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import agent, config, db, knowledge, ratelimit, security
from .schemas import (
    AdminMessageRequest,
    ChatRequest,
    LoginRequest,
)

app = FastAPI(title="Avatar", docs_url=None, redoc_url=None)


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Return dict-valued 401 details as the bare body (CONTRACT.md §7/§9), e.g.
    ``{"error":"unauthorized"}`` rather than FastAPI's nested ``{"detail": ...}``.
    All other HTTPExceptions keep the default envelope.
    """
    if exc.status_code == 401 and isinstance(exc.detail, dict):
        return JSONResponse(
            status_code=401, content=exc.detail, headers=getattr(exc, "headers", None)
        )
    return await http_exception_handler(request, exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _initials(name: Optional[str]) -> str:
    """Two-letter initials from a name/handle; falls back to a visitor mark."""
    name = (name or "").strip()
    if not name:
        return "?"
    parts = [p for p in name.replace("-", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _conversation_name(rows: list[dict[str, Any]]) -> Optional[str]:
    """Latest non-null ``conversation_name`` among the rows (rows are asc)."""
    name: Optional[str] = None
    for row in rows:
        value = row.get("conversation_name")
        if value:
            name = value
    return name


def _thread_payload(conversation_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Shape a list of rows into the public/admin thread response."""
    messages = [
        {
            "id": row.get("id"),
            "role": row.get("role"),
            "content": row.get("content", ""),
            "tool_calls": row.get("tool_calls"),
            "needs_attention": bool(row.get("needs_attention")),
            "read": bool(row.get("read")),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]
    return {
        "conversation_id": conversation_id,
        "conversation_name": _conversation_name(rows),
        "messages": messages,
    }


def _sse(payload: dict[str, Any]) -> str:
    """Encode one SSE event line (``data: <json>\\n\\n``)."""
    return f"data: {json.dumps(payload)}\n\n"


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


# ---------------------------------------------------------------------------
# Public config
# ---------------------------------------------------------------------------


@app.get("/api/config")
def get_config() -> dict[str, str]:
    """Public runtime config for the frontend (owner name + model)."""
    return {"owner_name": config.OWNER_NAME, "model": config.MODEL}


# ---------------------------------------------------------------------------
# Chat (SSE)
# ---------------------------------------------------------------------------


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Stream the Avatar reply as Server-Sent Events (CONTRACT.md §7)."""
    conversation_id = req.conversation_id
    visitor_name = (req.visitor_name or "").strip() or None

    # 1. Rate limit — before any LLM call or DB write.
    if not ratelimit.allow(conversation_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limited",
                "detail": "You're sending messages too quickly. Please slow down.",
            },
        )

    # 2. Truncate over-long messages (stored AND sent to the LLM).
    message = req.message or ""
    if len(message) > config.MAX_MESSAGE_CHARS:
        message = message[: config.MAX_MESSAGE_CHARS] + config.TRUNCATION_NOTE

    # 3. Persist the visitor message.
    db.insert_visitor_message(conversation_id, message, visitor_name)

    # 4. Qn instant answer — no LLM.
    qn = knowledge.detect_qn(message)
    if qn is not None:
        answer = knowledge.instant_answer(qn)
        avatar_row = db.insert_avatar_message(
            conversation_id, answer, tool_calls=None, needs_attention=False
        )

        async def instant_stream() -> AsyncGenerator[str, None]:
            yield _sse({"type": "meta", "conversation_id": conversation_id})
            yield _sse({"type": "delta", "text": answer})
            yield _sse(
                {
                    "type": "done",
                    "message_id": avatar_row.get("id"),
                    "created_at": avatar_row.get("created_at"),
                    "tool_calls": None,
                    "needs_attention": False,
                }
            )

        return StreamingResponse(
            instant_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
        )

    # 5. LLM path — build prompt from the full thread, stream the agent.
    from .prompt import build_instructions, build_transcript

    thread = db.get_conversation(conversation_id)
    instructions = build_instructions()
    transcript = build_transcript(thread, message, visitor_name)

    async def llm_stream() -> AsyncGenerator[str, None]:
        yield _sse({"type": "meta", "conversation_id": conversation_id})
        full_text = ""
        tool_calls: list[dict[str, Any]] = []
        push_fired = False
        try:
            async for event in agent.stream_reply(transcript, instructions):
                kind = event[0]
                if kind == "delta":
                    chunk = event[1]
                    full_text += chunk
                    yield _sse({"type": "delta", "text": chunk})
                elif kind == "tool_called":
                    name = event[1]
                    args = event[2] if len(event) > 2 else None
                    if name == "push_tool":
                        push_fired = True
                    entry: dict[str, Any] = {"tool": name}
                    if args is not None:
                        entry["args"] = args
                    tool_calls.append(entry)
                    detail = args if isinstance(args, str) else None
                    yield _sse(
                        {
                            "type": "tool",
                            "tool": name,
                            "phase": "called",
                            "detail": detail,
                        }
                    )
                elif kind == "tool_output":
                    name = event[1]
                    yield _sse(
                        {"type": "tool", "tool": name, "phase": "output"}
                    )
        except Exception as exc:  # surface a clean SSE error, never 500 mid-stream
            yield _sse({"type": "error", "detail": str(exc)})
            return

        avatar_row = db.insert_avatar_message(
            conversation_id,
            full_text,
            tool_calls=tool_calls or None,
            needs_attention=push_fired,
        )
        yield _sse(
            {
                "type": "done",
                "message_id": avatar_row.get("id"),
                "created_at": avatar_row.get("created_at"),
                "tool_calls": tool_calls or None,
                "needs_attention": push_fired,
            }
        )

    return StreamingResponse(
        llm_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


# ---------------------------------------------------------------------------
# Public conversation fetch (resume + polling)
# ---------------------------------------------------------------------------


@app.get("/api/conversation/{conversation_id}")
def get_conversation(conversation_id: str) -> dict[str, Any]:
    """Full thread for resume + polling. Empty messages for unknown ids (200)."""
    rows = db.get_conversation(conversation_id)
    return _thread_payload(conversation_id, rows)


# ---------------------------------------------------------------------------
# Admin: auth
# ---------------------------------------------------------------------------


@app.post("/api/admin/login")
def admin_login(req: LoginRequest):
    """Validate the admin password; on success set the session cookie."""
    if not config.ADMIN_PASSWORD or req.password != config.ADMIN_PASSWORD:
        return JSONResponse(
            status_code=401, content={"error": "invalid_password"}
        )
    response = JSONResponse(
        content={"ok": True, "owner_name": config.OWNER_NAME}
    )
    security.set_session_cookie(response)
    return response


@app.post("/api/admin/logout")
def admin_logout():
    """Clear the admin session cookie."""
    response = JSONResponse(content={"ok": True})
    security.clear_session_cookie(response)
    return response


@app.get("/api/admin/me")
def admin_me(request: Request) -> dict[str, Any]:
    """Report auth state without 401 (used to gate the admin UI)."""
    return {
        "authenticated": security.is_authenticated(request),
        "owner_name": config.OWNER_NAME,
    }


# ---------------------------------------------------------------------------
# Admin: data (guarded)
# ---------------------------------------------------------------------------


@app.get("/api/admin/conversations")
def admin_conversations(_: bool = Depends(security.require_admin)):
    """Inbox aggregated in Python from the messages table, most-recent first."""
    rows = db.list_all_messages()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["conversation_id"], []).append(row)

    summaries: list[dict[str, Any]] = []
    for cid, msgs in grouped.items():
        msgs.sort(key=lambda r: (r.get("created_at") or "", r.get("id") or 0))
        last = msgs[-1]
        name = _conversation_name(msgs)
        preview = (last.get("content") or "").strip().replace("\n", " ")
        if len(preview) > 140:
            preview = preview[:140].rstrip() + "…"
        unread_count = sum(1 for m in msgs if not m.get("read"))
        needs_attention = any(m.get("needs_attention") for m in msgs)
        summaries.append(
            {
                "conversation_id": cid,
                "name": name,
                "initials": _initials(name),
                "preview": preview,
                "last_role": last.get("role"),
                "last_at": last.get("created_at"),
                "message_count": len(msgs),
                "unread_count": unread_count,
                "needs_attention": needs_attention,
            }
        )

    summaries.sort(key=lambda s: (s.get("last_at") or ""), reverse=True)
    return summaries


@app.get("/api/admin/conversation/{conversation_id}")
def admin_open_conversation(
    conversation_id: str, _: bool = Depends(security.require_admin)
) -> dict[str, Any]:
    """Open a thread: mark all rows read + clear attention, return the thread."""
    rows = db.open_conversation(conversation_id)
    return _thread_payload(conversation_id, rows)


@app.post("/api/admin/conversation/{conversation_id}/message")
def admin_post_message(
    conversation_id: str,
    req: AdminMessageRequest,
    _: bool = Depends(security.require_admin),
) -> dict[str, Any]:
    """Insert an owner (human) message. The Avatar does not react (SPEC Q&A #4)."""
    row = db.insert_human_message(conversation_id, req.content)
    return {
        "id": row.get("id"),
        "role": row.get("role"),
        "content": row.get("content", ""),
        "tool_calls": row.get("tool_calls"),
        "needs_attention": bool(row.get("needs_attention")),
        "read": bool(row.get("read")),
        "created_at": row.get("created_at"),
    }


# ---------------------------------------------------------------------------
# Static frontend serving (registered AFTER the API routes)
# ---------------------------------------------------------------------------

_DIST = config.FRONTEND_DIST
_INDEX = _DIST / "index.html"
_ADMIN = _DIST / "admin.html"

_DEV_NOTE = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>Avatar</title></head><body style='font-family:system-ui;"
    "max-width:40rem;margin:4rem auto;padding:0 1rem;line-height:1.5'>"
    "<h1>Avatar backend is running</h1>"
    "<p>The frontend build was not found at "
    "<code>frontend/dist</code>. Build the frontend "
    "(<code>npm run build</code>) to serve the visitor and admin pages here. "
    "The API is available under <code>/api</code>.</p>"
    "</body></html>"
)


# The Vite build fingerprints every asset (e.g. ``bubbles-<hash>.js``), so those
# are safe to cache forever. The HTML entry points, however, reference the
# current hashes; if a browser caches an old index.html, after a redeploy it
# requests asset hashes that no longer exist (404) and the app breaks until a
# hard refresh. Serve the HTML with ``no-cache`` so the browser always
# revalidates it while still caching the hashed assets aggressively.
_HTML_NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/", include_in_schema=False)
def serve_index():
    """Serve the visitor page, or a friendly note when the build is absent."""
    if _INDEX.is_file():
        return FileResponse(_INDEX, headers=_HTML_NO_CACHE)
    return HTMLResponse(_DEV_NOTE)


@app.get("/admin", include_in_schema=False)
def serve_admin():
    """Serve the admin page, or a friendly note when the build is absent."""
    if _ADMIN.is_file():
        return FileResponse(_ADMIN, headers=_HTML_NO_CACHE)
    return HTMLResponse(_DEV_NOTE)


# Mount the built assets and any other static files from dist/. Done last so
# that all explicit routes above take precedence. Only mounted when present.
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="static")
