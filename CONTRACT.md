# Avatar — Build Contract (authoritative integration spec)

This is the single source of truth that every build agent consumes so the backend, frontend,
infra, and tests integrate cleanly. **SPEC.md governs behaviour; `design-system/` governs
appearance; this file pins the exact interfaces between pieces.** When in doubt: SPEC for
behaviour, mockups for appearance, this file for the wire contract.

Owner is **Emil Dermendzhiev** / **E&P Systems** (read `OWNER_NAME` from env, never hardcode).

---

## 0. File ownership (disjoint — agents must stay in their lane)

| Agent | OWNS (writes only here) | May READ |
|---|---|---|
| BACKEND | `backend/app/**` | everything |
| FRONTEND | `frontend/**` | everything (esp. `design-system/`, this file) |
| INFRA | root `Dockerfile`, `.dockerignore`, `.env.example`, `scripts/start_mac.sh`, `scripts/stop_mac.sh`, `scripts/start_pc.ps1`, `scripts/stop_pc.ps1`, `scripts/fly.toml`, `scripts/deploy.sh`, `scripts/wordpress-embed.html` | everything |
| TESTPLAN | `test/**` (markdown only) | everything |
| BACKEND-PYTEST | `backend/tests/test_*.py` (NEW files only; never edit `test_supabase_connection.py`) | everything |

Do **not** touch: `SPEC.md`, `README.md`, `DEPLOY.md`, `CLAUDE.md`, `knowledge/**`,
`design-system/**` (read-only), `scripts/gen_avatars.py`, `.env`, `backend/pyproject.toml`
(deps already complete), `backend/tests/test_supabase_connection.py`.
Do **not** run `uv sync`, `npm install`, `docker`, or `git` — write files only; the orchestrator
integrates, installs, builds, and runs. Light static checks (`python -m py_compile`) are fine.

---

## 1. Environment variables (all via python-dotenv from project-root `.env`)

| Var | Meaning | Default in `config.py` |
|---|---|---|
| `OPENROUTER_API_KEY` | LLM key (OpenRouter) | required (no default) |
| `MODEL` | OpenRouter model id (`openai/...`) | `openai/gpt-5.4-nano` |
| `OWNER_NAME` | person the twin represents | `Emil Dermendzhiev` (config default; always set in `.env`) |
| `ADMIN_PASSWORD` | admin login password | required |
| `PUSHOVER_USER`, `PUSHOVER_TOKEN` | Pushover creds | optional (push tool no-ops gracefully if unset) |
| `SUPABASE_URL`, `SUPABASE_KEY` | Supabase (secret key) | required |
| `SESSION_SECRET` | signs admin cookie | `avatar::{ADMIN_PASSWORD}` if unset |
| `COOKIE_SECURE` | `1` → Secure cookie (HTTPS) | `0` |

`config.py` loads `.env` from the **project root** (`Path(__file__).resolve().parents[2] / ".env"`)
with `override=True`, exposes the values as module constants, and computes `SESSION_SECRET`
fallback. It also resolves `KNOWLEDGE_DIR = <root>/knowledge`.

---

## 2. Data model — `public.messages` (already created in Supabase)

```
id              bigint identity PK
conversation_id uuid not null
conversation_name text  null      -- visitor's entered name/initials (latest non-null wins)
role            text  not null    -- 'visitor' | 'avatar' | 'human'
content         text  not null
tool_calls      jsonb null        -- list of {tool, args, result_summary}; `args` is the raw SDK
                                  -- arguments as a JSON **string** (e.g. '{"question_number":3}'),
                                  -- NOT a parsed object — frontend must parse defensively.
needs_attention boolean default false  -- set on the avatar row when push_tool fired
read            boolean default false  -- human has seen it in admin
created_at      timestamptz default now()
```

Insert rules:
- visitor message → `role='visitor'`, `read=false`, `conversation_name=<name or omit>`.
- avatar message → `role='avatar'`, `read=false`, `tool_calls=<list|null>`,
  `needs_attention=<true iff push_tool fired this turn>`.
- human (owner) message → `role='human'`, `read=true`, `needs_attention=false`.

A conversation is **unread** iff any row has `read=false`; **needs-attention** iff any row has
`needs_attention=true`. Opening it in admin sets `read=true, needs_attention=false` on every row.

Use `supabase-py` (`create_client(SUPABASE_URL, SUPABASE_KEY)`). All DB access is in
`backend/app/db.py` (a thin data layer); no other module talks to Supabase directly.

---

## 3. Backend module layout (`backend/app/`)

```
backend/app/
  __init__.py
  config.py        env constants + paths (see §1)
  db.py            Supabase data layer (all queries live here)
  knowledge.py     load knowledge.md, style.md, faq.jsonl; FAQ lookup + Qn detection
  prompt.py        build system instructions + the single-user-prompt transcript (§5)
  tools.py         faq_tool, push_tool (Agents SDK @function_tool) + push() helper
  agent.py         build the Agent + OpenRouter model; stream a reply (§4)
  security.py      admin session: sign/verify cookie, FastAPI dependency `require_admin`
  ratelimit.py     moving-window limiter (limits pkg), 20/min per conversation_id
  schemas.py       pydantic request/response models
  main.py          FastAPI app: API routes + static serving (§6, §7, §8)
```

`main.py` is the only entrypoint: `uvicorn app.main:app`. It must run from `backend/` with
`--app-dir .` (so `app` is importable). It serves the built frontend (see §8).

---

## 4. LLM via OpenAI Agents SDK + OpenRouter (idiomatic)

Use the Chat-Completions model adapter pointed at OpenRouter, and disable tracing (OpenRouter has
no OpenAI tracing endpoint):

```python
from openai import AsyncOpenAI
from agents import Agent, Runner, OpenAIChatCompletionsModel, set_tracing_disabled
from openai.types.responses import ResponseTextDeltaEvent

set_tracing_disabled(True)
_client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
_model = OpenAIChatCompletionsModel(model=MODEL, openai_client=_client)

agent = Agent(name="Avatar", instructions=<system prompt>, model=_model,
              tools=[faq_tool, push_tool])
result = Runner.run_streamed(agent, input=<single user prompt>)
async for ev in result.stream_events():
    # raw token deltas:
    if ev.type == "raw_response_event" and isinstance(ev.data, ResponseTextDeltaEvent):
        yield ("delta", ev.data.delta)
    elif ev.type == "run_item_stream_event":
        if ev.name == "tool_called":
            yield ("tool_called", <tool name>, <args>)
        elif ev.name == "tool_output":
            yield ("tool_output", <tool name>)
```

`agent.py` exposes an async generator `stream_reply(transcript:str, instructions:str)` yielding
typed tuples the route layer maps to SSE. It accumulates the full text and the list of tool calls,
and records whether `push_tool` fired (for `needs_attention`). Tool detection for
`needs_attention`: track tool names seen in `tool_called` events.

**Do not** call OpenAI directly anywhere; everything goes through the Agents SDK + OpenRouter
client. No streaming to disk; no SQLite session (we rebuild the transcript ourselves each turn —
see §5).

---

## 5. Prompt composition (`prompt.py`)

This is a **3-way** conversation (visitor ↔ Avatar ↔ human owner). The Avatar is the twin of
`OWNER_NAME`. Per SPEC: one system prompt + **one user prompt** that summarizes the whole
conversation (because of the human role we cannot use plain user/assistant turns).

`build_instructions()` → system prompt, composed in this order:
1. **Role**: "You are the digital twin (an AI) of {OWNER_NAME}, chatting with visitors on
   {OWNER_NAME}'s website. You represent {OWNER_NAME}; answer about their career, background,
   skills, work and services in the first person as the twin. If asked, say clearly you are an AI
   digital twin of {OWNER_NAME}."
2. **Three-way context**: explain that {OWNER_NAME} (the real human) may personally join the
   conversation; their messages are labelled as the human/owner and are the real person speaking.
   The Avatar must **not** impersonate, repeat, or contradict the human's messages, and must not
   reply on the human's behalf — treat them as authoritative context.
3. **Who I am** — full contents of `knowledge/knowledge.md`.
4. **Voice & rules** — full contents of `knowledge/style.md`.
5. **FAQ routing** — "Your `faq_tool` returns full answers to common questions by number. If the
   visitor's question matches one, call `faq_tool` with that number and answer in the original
   markdown." Then a numbered list of the concise `query` phrasings: `\n{faq}. {query}`.
6. **Tools & contact**: use `faq_tool` for known questions; if the visitor wants to get in touch,
   ask for their email then call `push_tool` to notify the owner; if you cannot answer or it needs
   the human, call `push_tool` to notify the owner AND tell the visitor you've done so. Never
   invent information.
7. **Formatting**: markdown, no code blocks, clickable links — defer to style.md.

`build_transcript(messages, latest_visitor_message, visitor_name)` → the single user prompt: a
readable transcript of all prior messages, each prefixed by role:
- visitor → `Visitor{ " ("+name+")" if name }: {content}`
- avatar  → `You (the Avatar): {content}`
- human   → `{OWNER_NAME} (the human, joined live): {content}`
Then a trailing instruction: `Respond as the Avatar to the latest visitor message.` The latest
visitor message is included as the final visitor line. Keep it plain text.

---

## 6. Tools (`tools.py`)

```python
@function_tool
def faq_tool(question_number: int) -> str:
    """Retrieve the full answer to a frequently asked question by its number."""
    # returns "### Question {n}:\n{question}\n### Answer:\n{answer}" or a not-found note
```

```python
@function_tool
def push_tool(message: str) -> str:
    """Notify the human owner ({OWNER_NAME}) via Pushover push notification.
    Use when the visitor wants to get in touch (after collecting their email) or when a
    question needs the human / cannot be answered."""
    # POST to https://api.pushover.net/1/messages.json with PUSHOVER_USER/TOKEN
    # if creds unset: return a benign message, do not raise
```

`faq_tool` reads from the loaded FAQ (see `knowledge.py`). Keep a module-level loaded FAQ.

---

## 7. HTTP API (all JSON unless noted; prefix `/api`)

### Public (no auth; possession of `conversation_id` UUID = access)

**`POST /api/chat`** → streams the Avatar reply as **SSE** (`text/event-stream`).
Request body:
```json
{ "conversation_id": "<uuid>", "message": "<text>", "visitor_name": "<optional>" }
```
Server flow (in order):
1. **Rate limit**: moving window 20/min per `conversation_id`. If exceeded → **HTTP 429** JSON
   `{ "error": "rate_limited", "detail": "You're sending messages too quickly. Please slow down." }`
   **before** any LLM call or DB write.
2. **Truncate**: if `len(message) > 20000`, set `message = message[:20000] +
   "\n\n[...message truncated as it's too long; ask the visitor to send something more concise]"`.
   The truncated text is what gets stored AND sent to the LLM.
3. Persist the visitor message (role=visitor, conversation_name from `visitor_name` if non-empty).
4. **Qn instant answer**: if message matches `^\s*[Qq](\d+)\s*$` → NO LLM. Compute
   `answer = "**Q{n}:** {question}\n\n{answer}"` from the FAQ (or a friendly not-found). Persist as
   role=avatar (`tool_calls=null`, `needs_attention=false`). Stream it as a single `delta` then
   `done`. (Frontend shows the `.qn-tag` on the visitor turn by detecting the `Qn` pattern itself.)
5. Otherwise: load the full thread, build instructions + transcript, run the agent streamed.
   Emit SSE events as they arrive; accumulate text + tool calls; on completion persist the avatar
   message (with `tool_calls`, and `needs_attention=true` iff push_tool fired), then emit `done`.

**SSE framing**: each event is one `data: <json>\n\n` line. The JSON has a `type`:
```
{"type":"meta","conversation_id":"<uuid>"}                      // first, optional
{"type":"tool","tool":"faq_tool"|"push_tool","phase":"called"|"output","detail":"<optional>"}
{"type":"delta","text":"<chunk>"}
{"type":"done","message_id":<int>,"created_at":"<iso>","tool_calls":[...],"needs_attention":bool}
{"type":"error","detail":"<msg>"}
```
Set headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`.

**`GET /api/conversation/{conversation_id}`** → full thread for resume + polling.
```json
{ "conversation_id":"<uuid>", "conversation_name":"<str|null>",
  "messages":[ {"id":1,"role":"visitor","content":"...","tool_calls":null,
                "needs_attention":false,"read":false,"created_at":"<iso>"}, ... ] }
```
Ordered by `created_at` asc. `conversation_name` = latest non-null among the rows (no extra query).
Returns empty `messages: []` for unknown ids (200, not 404).

### Admin (guarded by signed session cookie — see §9)

**`POST /api/admin/login`** body `{ "password": "..." }` → on match: set cookie, `200 {"ok":true,
"owner_name":"<OWNER_NAME>"}`. On mismatch: `401 {"error":"invalid_password"}`.
**`POST /api/admin/logout`** → clears cookie, `200 {"ok":true}`.
**`GET /api/admin/me`** → `200 {"authenticated":bool,"owner_name":"<OWNER_NAME>"}` (no 401; used to
gate the UI).
**`GET /api/admin/conversations`** → inbox, most-recent first:
```json
[ {"conversation_id":"<uuid>","name":"<str|null>","initials":"EK",
   "preview":"<last content, trimmed>","last_role":"visitor","last_at":"<iso>",
   "message_count":7,"unread_count":2,"needs_attention":true} , ... ]
```
Aggregate in Python from the messages table (works on any README-provisioned DB; no custom views).
**`GET /api/admin/conversation/{conversation_id}`** → open a thread. Single PostgREST
update-returning marks all rows `read=true, needs_attention=false` and returns them; respond with
the same thread shape as the public fetch. (If the conversation has no rows, return empty thread.)
**`POST /api/admin/conversation/{conversation_id}/message`** body `{ "content":"..." }` → insert
role=human (`read=true`), return the inserted row. The Avatar does **not** react (SPEC Q&A #4).

All `/api/admin/*` except `login`/`me` require a valid session (FastAPI dependency `require_admin`
→ 401 JSON `{"error":"unauthorized"}` when missing/invalid).

---

## 8. Static serving (`main.py`)

The built frontend lives in `frontend/dist/` (Vite multi-page build → `dist/index.html` +
`dist/admin.html` + `dist/assets/**`). The backend serves it:
- `GET /` → `dist/index.html` (visitor)
- `GET /admin` → `dist/admin.html`
- `GET /assets/*` and other build files → from `dist/`
- API routes are registered **before** the catch-all static mount so `/api/*` wins.
If `dist/` is absent (pure-backend dev), `/` returns a small friendly note (don't crash). Mount
order: API routers first, then `StaticFiles`/explicit file responses.

---

## 9. Admin session (`security.py`)

- `itsdangerous.URLSafeTimedSerializer(SESSION_SECRET, salt="avatar-admin")`.
- On login success, set cookie `avatar_admin` = `serializer.dumps({"admin": true})`, attrs:
  `httponly=True, samesite="lax", secure=(COOKIE_SECURE=="1"), max_age=7*24*3600, path="/"`.
- `require_admin`: read cookie, `serializer.loads(token, max_age=...)`; on failure raise
  `HTTPException(401, {"error":"unauthorized"})`.

---

## 10. Frontend (`frontend/`, vanilla TS + Vite, multi-page)

Structure:
```
frontend/
  package.json            deps: vite, typescript, marked (md), dompurify (sanitize)
  tsconfig.json
  vite.config.ts          multipage: index.html + admin.html; dev proxy /api -> :8000
  index.html              visitor page (loads theme pre-paint script)
  admin.html              admin page (loads theme pre-paint script)
  public/
    icons.svg             copied from design-system/
    assets/avatar-*.png   copied from design-system/assets/ (already Emil's)
    favicon ...
  src/
    styles/tokens.css        copied from design-system/  (load 1st)
    styles/components.css     copied from design-system/  (load 2nd)
    styles/visitor.css        page CSS (load 3rd)
    styles/admin.css          page CSS (load 3rd)
    lib/api.ts                fetch helpers + SSE stream parser for POST /api/chat
    lib/markdown.ts           marked + DOMPurify render
    lib/theme.ts              get/set localStorage['avatar-theme'], toggle, set [data-theme]
    lib/icons.ts              `<svg class="icon"><use href="/icons.svg#i-..."/></svg>` helper
    lib/dom.ts                tiny element helpers, initials(name), formatTime(iso)
    visitor.ts               visitor app
    admin.ts                 admin app
```
Load CSS order always: **tokens.css → components.css → page.css** (SKILL.md). Set theme before
first paint: `document.documentElement.setAttribute('data-theme', localStorage.getItem('avatar-theme')||'dark')`.
Import Google Fonts via tokens.css `@import` (already present).

Owner name + subtitle come from the backend at runtime: call `GET /api/admin/me` (admin) and embed
`OWNER_NAME` on the visitor page via a tiny `GET /api/config` → `{"owner_name":"...",
"examples":[...]}`. **Add this endpoint to the backend** (public, no auth):
`GET /api/config` → `{ "owner_name": "<OWNER_NAME>", "model": "<MODEL>" }`. The frontend renders the
brand subtitle, page `<title>`, and the twin's name from `owner_name` — never hardcode it.

Behaviour contract — implement exactly per SPEC + `design-system/docs/ux-flows.md`:
- **Visitor**: conversation_id UUID (crypto.randomUUID); "Keep chat" switch (default on) persists id
  in a cookie `avatar_cid` (SameSite=Lax) and restores the thread via `GET /api/conversation/{id}`;
  Reset clears thread + new id. Composer focus on load and after send (`{preventScroll:true}`).
  Enter sends, Shift+Enter newline. SSE streaming with `.tool-line` (cyan faq / yellow push) then
  bubble fills; `.typing` before first token. Intro state with `.prompt-chip` examples (submit on
  click). Bare `Qn` shows `.qn-tag` on the visitor bubble; reply restates the question. Deep link
  `?q=N` auto-submits `Qn` on load then strips the param (`history.replaceState`). Poll
  `GET /api/conversation/{id}` every 10s, backing off to 60s after 5 min idle, to pick up human
  `.msg--human` bubbles (ring + tint + glow + "{OWNER_NAME} — live"). 429 → friendly inline line.
  Theme toggle persists. Footer links: LinkedIn (https://www.linkedin.com/in/emildermendzhiev-7a249a244),
  website (https://epsystems.org), email (emildermendjiev9@gmail.com). No YouTube for this owner —
  omit or reuse website; do not invent a URL.
- **Admin**: login `.card`; on success show inbox + thread. Inbox most-recent-first with `.is-unread`
  (+ unread dot), `.needs-attention` (yellow row + bell-dot), `.is-active` (selection bar). Opening a
  thread calls `GET /api/admin/conversation/{id}` (marks read), scrolls to latest. Composer "Reply as
  {OWNER_NAME}" posts to the admin message endpoint → `.msg--human` bubble. ↑/↓ move conversations,
  Enter sends, Shift+Enter newline; `.kbd` hints. Poll the open thread (10s) for new visitor/avatar
  rows. Responsive master/detail ≤860px with `#i-back`. Refresh inbox periodically.
- Render message markdown via `lib/markdown.ts`. Times via `formatTime`. Initials via `initials()`.
- **Appearance**: compose from `components.css` classes; lift structure from
  `mockups/Visitor Chat.html` and `mockups/Admin Dashboard.html` (the tie-breaker). Dark default,
  light full peer. No emoji, no gradients in chrome, no purple except primary actions, yellow only
  for the human. Every color from tokens. Meet the SKILL.md acceptance checklist.

---

## 11. Tests

- `backend/tests/` (BACKEND-PYTEST): unit tests with the LLM and Supabase **mocked/faked** so they
  run without network: config loading + SESSION_SECRET fallback; knowledge loading + Qn detection +
  FAQ lookup; prompt composition (instructions contain knowledge/style/faq routing; transcript
  labels roles incl. human); truncation at 20000; rate limit returns 429 after 20; admin auth gating
  (every `/api/admin/*` data route returns 401 without cookie, 200 with); login/logout/me; Qn instant
  path writes 2 rows and skips the LLM; SSE happy path with a fake agent stream; conversation fetch
  shape; inbox aggregation (unread/needs-attention); open-thread marks read & clears attention; human
  message insert with role=human. Use FastAPI `TestClient`, monkeypatch `app.agent.stream_reply` and
  `app.db` (an in-memory fake), and a fake limiter clock where needed. Mark any test that truly calls
  the model with `@pytest.mark.llm`.
- `test/` (TESTPLAN): `backend-test-plan.md`, `frontend-test-plan.md`, `e2e-test-plan.md`, each a
  checklist mapped to SPEC requirements and the SKILL.md acceptance list. The orchestrator checks
  boxes after running.

---

## 12. Definition of done (per agent)

- BACKEND: `uvicorn app.main:app` imports clean; all routes present with the shapes above; no direct
  OpenAI/Supabase calls outside `agent.py`/`db.py`; graceful when `dist/` or Pushover creds absent.
- FRONTEND: `npm run build` produces `dist/index.html`, `dist/admin.html`, `dist/assets/**`; both
  pages composed from the design system; no unresolved `var()`; behaviour per §10.
- INFRA: single-container Docker (build frontend, then serve via backend on `:8000`); start/stop
  scripts for mac+pc that stop-then-rebuild-then-run with the root `.env`; fly.toml + deploy.sh.
- Everything reads `OWNER_NAME` from env; no hardcoded owner identity in shipped code.
