# Backend test plan

Comprehensive checklist for the FastAPI backend. Items map to **SPEC.md** (behaviour + the Q&A
section) and **CONTRACT.md** (the wire contract, especially §1–§9, §11). The companion pytest suite
lives in `backend/tests/` (BACKEND-PYTEST owns those files); this plan is the human-readable map the
orchestrator checks off after running them.

Conventions for execution: the LLM and Supabase are **mocked/faked** so the suite runs offline
(CONTRACT §11). Use FastAPI `TestClient`, monkeypatch `app.agent.stream_reply` with a fake async
generator, replace `app.db` with an in-memory fake, and inject a controllable clock into the limiter
where needed. Any test that truly calls the model is marked `@pytest.mark.llm` and is excluded from
the default offline run. Per SPEC, when exercising the real model set `MODEL=openai/gpt-5.4-nano` to
keep costs low; delete any test conversation rows from Supabase afterwards.

SPEC traceability: each section header cites the SPEC and CONTRACT clauses it verifies.

---

## 1. Configuration & environment (SPEC "Setup and Validation"; CONTRACT §1)

- [x] `config.py` loads `.env` from the **project root** via `Path(__file__).resolve().parents[2] / ".env"` with `override=True`.
- [x] `OPENROUTER_API_KEY`, `ADMIN_PASSWORD`, `SUPABASE_URL`, `SUPABASE_KEY` are exposed as module constants.
- [x] `MODEL` defaults to `openai/gpt-5.4-nano` when unset in the environment.
- [x] `OWNER_NAME` falls back to `Ed Donner` when unset, and reflects `Emil Dermendzhiev` (or whatever is in `.env`) when set — never hardcoded elsewhere in shipped code.
- [x] `SESSION_SECRET` falls back to `avatar::{ADMIN_PASSWORD}` when unset, and uses the explicit value when set.
- [x] `COOKIE_SECURE` parses `"1"` as secure-cookie on; unset/`"0"` as off.
- [x] `PUSHOVER_USER` / `PUSHOVER_TOKEN` are optional (absence does not raise at import time).
- [x] `KNOWLEDGE_DIR` resolves to `<project-root>/knowledge` and exists.
- [x] Importing `app.main` (and `uvicorn app.main:app`) succeeds with a complete `.env` — no import-time crashes.

## 2. Knowledge loading, Qn detection & FAQ lookup (SPEC Q&A #3; CONTRACT §5–§6)

- [x] `knowledge.py` loads `knowledge/knowledge.md` and `knowledge/style.md` as non-empty strings.
- [x] `faq.jsonl` parses to a list where each row has `faq` (int), `question`, `answer`, and `query`.
- [x] FAQ lookup by number returns the full original `question` + `answer` for a valid number (e.g. #2 returns Emil's technical-background answer).
- [x] FAQ lookup for an out-of-range / unknown number returns a graceful not-found note (no exception).
- [x] Qn detection matches `^\s*[Qq](\d+)\s*$` — accepts `Q2`, `q2`, ` Q2 `, ` q07 `; rejects `Q`, `Q2 please`, `What is Q2`, `2`, empty string.
- [x] The Qn instant answer string is formatted `**Q{n}:** {question}\n\n{answer}` (restates the question before the answer, per SPEC).
- [x] A Qn with no matching FAQ number yields a friendly not-found reply (not a 500).

## 3. Prompt composition — instructions (SPEC "LLM call" + Q&A #3,#4,#11; CONTRACT §5)

- [x] `build_instructions()` includes the role framing: digital twin (an AI) of `OWNER_NAME`, first person, says it is an AI twin if asked.
- [x] Instructions contain the **three-way** context: the real human `OWNER_NAME` may join; their messages are authoritative; the Avatar must not impersonate, contradict, or reply on the human's behalf.
- [x] Instructions embed the **full** contents of `knowledge.md` (Who I am).
- [x] Instructions embed the **full** contents of `style.md` (Voice & rules).
- [x] Instructions include the FAQ routing block plus the numbered list of concise `query` phrasings (`{faq}. {query}`).
- [x] Instructions describe `faq_tool` for known questions and `push_tool` for contact / unanswerable / needs-human, with the instruction to tell the visitor when the owner was notified, and "never invent information".
- [x] Instructions reference markdown formatting / clickable links / no code blocks (defer to style.md).
- [x] `OWNER_NAME` appears interpolated from config, not as a literal hardcoded name.

## 4. Prompt composition — transcript (SPEC "user prompt summarizes the conversation"; CONTRACT §5)

- [x] `build_transcript(...)` produces a **single** plain-text user prompt (not user/assistant turns).
- [x] Visitor lines render as `Visitor: {content}`; with a name as `Visitor ({name}): {content}`.
- [x] Avatar lines render as `You (the Avatar): {content}`.
- [x] Human lines render as `{OWNER_NAME} (the human, joined live): {content}`.
- [x] The transcript ends with the latest visitor message and the trailing instruction `Respond as the Avatar to the latest visitor message.`
- [x] Prior messages appear in chronological order.

## 5. Input truncation (SPEC abuse guards / Q&A #12; CONTRACT §7 step 2)

- [x] A message of exactly 20,000 chars is **not** truncated.
- [x] A message > 20,000 chars is truncated to 20,000 then the note `\n\n[...message truncated as it's too long; ask the visitor to send something more concise]` is appended.
- [x] The truncated text is what gets **persisted** (visitor row content) AND what is **sent to the LLM** (appears in the transcript).
- [x] Truncation runs before the LLM call and before persistence.

## 6. Rate limiting — 429 (SPEC Q&A #12; CONTRACT §7 step 1)

- [x] The limiter is a moving window of **20 messages / minute** keyed per `conversation_id`.
- [x] The 21st request within the window returns **HTTP 429** with body `{"error":"rate_limited","detail":"You're sending messages too quickly. Please slow down."}`.
- [x] The 429 fires **before** any LLM call and **before** any DB write (no visitor row persisted on a rejected request).
- [x] Two different `conversation_id`s have independent budgets (one being limited does not affect the other).
- [x] After the window advances (controllable clock), requests are accepted again.

## 7. Admin authentication gating (SPEC Q&A #6; CONTRACT §7, §9)

- [x] `GET /api/admin/conversations` → **401** `{"error":"unauthorized"}` without a valid cookie; **200** with one.
- [x] `GET /api/admin/conversation/{id}` → **401** without cookie; **200** with cookie.
- [x] `POST /api/admin/conversation/{id}/message` → **401** without cookie; **200/201** with cookie.
- [x] `POST /api/admin/logout` → requires a valid session (per "all `/api/admin/*` except login/me").
- [x] `POST /api/admin/login` and `GET /api/admin/me` are reachable **without** a cookie (the two exceptions).
- [x] A tampered / malformed / wrong-salt cookie is rejected (401) by `require_admin`.
- [x] An expired session token (past `max_age`) is rejected (401).
- [x] The cookie is `httponly`, `samesite=lax`, `secure` only when `COOKIE_SECURE=="1"`, `path="/"`, `max_age=7*24*3600`.

## 8. Login / logout / me (CONTRACT §7 admin block)

- [x] `POST /api/admin/login` with the correct `ADMIN_PASSWORD` → 200 `{"ok":true,"owner_name":"<OWNER_NAME>"}` and sets the `avatar_admin` cookie.
- [x] `POST /api/admin/login` with a wrong password → 401 `{"error":"invalid_password"}` and sets no cookie.
- [x] `POST /api/admin/logout` clears the cookie → 200 `{"ok":true}`; subsequent guarded calls are 401.
- [x] `GET /api/admin/me` with no cookie → 200 `{"authenticated":false,"owner_name":"<OWNER_NAME>"}` (never 401).
- [x] `GET /api/admin/me` with a valid cookie → 200 `{"authenticated":true,"owner_name":"<OWNER_NAME>"}`.

## 9. Qn instant path on `/api/chat` (SPEC; CONTRACT §7 step 4)

- [x] A `Qn` message persists **two** rows: visitor (role=visitor) then avatar (role=avatar) and makes **no** LLM call (`stream_reply` not invoked).
- [x] The avatar row for a Qn has `tool_calls=null` and `needs_attention=false`.
- [x] The streamed response is a single `delta` with the `**Q{n}:** {question}\n\n{answer}` text followed by a `done` event.
- [x] A `Qn` whose number is unknown still persists an avatar row with a friendly not-found message and emits `delta`+`done`.
- [x] The Qn path still respects rate-limit (429 before processing) and truncation ordering.

## 10. SSE happy path on `/api/chat` (SPEC streaming Q&A #9; CONTRACT §4, §7 step 5)

- [x] Response is `text/event-stream` with headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`.
- [x] Each SSE frame is a single `data: <json>\n\n` line; the JSON carries a `type`.
- [x] With a fake agent stream the route emits, in order: optional `meta`, any `tool` events, one or more `delta` events, then a terminal `done`.
- [x] `tool` events carry `tool` (`faq_tool`/`push_tool`), `phase` (`called`/`output`), optional `detail`.
- [x] On completion the avatar message is persisted with the accumulated text, the collected `tool_calls`, and `needs_attention=true` **iff** `push_tool` fired this turn (otherwise false).
- [x] The terminal `done` event includes `message_id`, `created_at`, `tool_calls`, `needs_attention`.
- [x] An exception inside the stream emits a `{"type":"error","detail":...}` frame rather than crashing the connection.
- [x] The visitor message is persisted with `conversation_name` taken from `visitor_name` only when non-empty (omitted/null when empty).
- [x] `@pytest.mark.llm` smoke test: a real nano call returns a non-empty streamed reply (run on demand only; clean up the row afterwards).

## 11. Public conversation fetch shape (CONTRACT §7 public block)

- [x] `GET /api/conversation/{id}` returns `{conversation_id, conversation_name, messages:[...]}`.
- [x] `messages` are ordered by `created_at` ascending.
- [x] Each message has `id, role, content, tool_calls, needs_attention, read, created_at`.
- [x] `conversation_name` = the latest non-null `conversation_name` among the rows (derived from the loaded rows, no extra query).
- [x] An unknown `conversation_id` returns **200** with `messages: []` (not 404).
- [x] `GET /api/config` (public, no auth) returns `{"owner_name":"<OWNER_NAME>","model":"<MODEL>"}`.

## 12. Inbox aggregation (SPEC admin sidebar; CONTRACT §7 admin block)

- [x] `GET /api/admin/conversations` returns a list **most-recent-first** (by `last_at`).
- [x] Each item has `conversation_id, name, initials, preview, last_role, last_at, message_count, unread_count, needs_attention`.
- [x] `unread_count` counts rows with `read=false`; an item is unread iff it has any `read=false` row.
- [x] `needs_attention` is true iff any row in the conversation has `needs_attention=true`.
- [x] `preview` is the last message's content, trimmed; `initials` derived from name (or a sensible fallback).
- [x] Aggregation is done in Python from the `messages` table (no custom DB view required).

## 13. Open thread marks read & clears attention (SPEC Q&A #5; CONTRACT §2, §7)

- [x] `GET /api/admin/conversation/{id}` sets `read=true` and `needs_attention=false` on **every** row of that conversation.
- [x] It returns the **updated** rows in the same shape as the public fetch (single PostgREST update-returning round trip).
- [x] After opening, the conversation no longer appears unread or needs-attention in the inbox aggregation.
- [x] Opening a conversation with no rows returns an empty thread (no error).

## 14. Human (owner) message insert (SPEC Q&A #4; CONTRACT §2, §7)

- [x] `POST /api/admin/conversation/{id}/message` inserts a row with `role='human'`, `read=true`, `needs_attention=false`.
- [x] The endpoint returns the inserted row (full message shape).
- [x] Posting a human message does **not** trigger the Avatar / any LLM call.
- [x] The human message subsequently appears in the public `GET /api/conversation/{id}` thread (so the visitor's poll picks it up) and in the next transcript sent to the LLM.

## 15. Tools (SPEC reference push.py; CONTRACT §6)

- [x] `faq_tool(question_number)` returns `"### Question {n}:\n{question}\n### Answer:\n{answer}"` for a valid number, and a not-found note otherwise.
- [x] `push_tool(message)` POSTs to `https://api.pushover.net/1/messages.json` with `PUSHOVER_USER`/`PUSHOVER_TOKEN` (mocked HTTP in unit tests).
- [x] With Pushover creds **unset**, `push_tool` returns a benign message and does **not** raise.
- [x] Both tools are registered on the Agent as `@function_tool`s.

## 16. Static serving & app wiring (CONTRACT §8)

- [x] API routers are registered **before** the static catch-all so `/api/*` always wins.
- [x] `GET /` serves `frontend/dist/index.html` when present; `GET /admin` serves `dist/admin.html`.
- [x] `/assets/*` and other build files are served from `dist/`.
- [x] When `dist/` is **absent**, `/` returns a small friendly note and the app does not crash (pure-backend dev mode).
- [x] No direct OpenAI calls exist outside `agent.py`; no direct Supabase calls exist outside `db.py`.
