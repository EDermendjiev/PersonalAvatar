# UX flows & states

The behaviour contract is owned by `SPEC.md`. This file translates it into the design/QA target:
each flow, plus a states matrix to build and test against. Where a detail is visual (color,
spacing, which token), `components.css` and the mockups are authoritative.

---

## Roles & color (the mental model)

| Role | Who | Color | Token | Avatar |
|---|---|---|---|---|
| Visitor | the person on the site | blue | `--role-visitor` | initials chip (`.avatar--visitor`) |
| Avatar | the AI digital twin | cyan | `--role-avatar` | `avatar-robot-round.png` (`.avatar--twin`) |
| Human | the owner, live | yellow | `--role-human` | `avatar-human.png` (`.avatar--owner`, ring + glow) |

The visitor never sees the admin. The owner sees everything. The Avatar never reacts to the
human's messages — they're just added to the thread and included next time the visitor submits
(per SPEC Q&A #4).

---

## Visitor Chat (`/`)

### Arrival
- A `conversation_id` (UUID) is assigned. If **Keep chat** is on (default), the browser reuses
  the id from its cookie and the server returns the thread so far.
- The composer **takes focus on load** (`input.focus({preventScroll:true})` — `preventScroll`
  matters when the app is embedded in an iframe).
- **Empty state:** intro copy + a few `.prompt-chip` examples. Clicking a chip submits it
  immediately.

### Header controls
- **Name field** — optional first name / initials; seeds the visitor's `.avatar--visitor` chip.
- **Keep chat** switch (`.switch`) — defaults **on**. Off → no cookie persistence.
- **Reset** (`.btn--icon`, `#i-reset`) — clears the thread and assigns a fresh `conversation_id`.
- **Theme toggle** — sun/moon; persists to `localStorage['avatar-theme']`.

### Sending
- **Enter** sends; **Shift+Enter** is a newline. After send, the composer **regains focus**.
- The Avatar's reply **streams via SSE**. While tools run, a small mono `.tool-line` shows the
  call (e.g. `faq_tool · "automation"`); then the `.msg__bubble` fills in. A `.typing` indicator
  may precede the first token.
- `push_tool` renders as `.tool-line--push` (yellow bell): the Avatar has notified the owner.
  The bubble should say so in words too.

### `Qn` instant answers
- A bare `Qn` (e.g. `Q2`) returns FAQ #n with **no LLM call**. The visitor turn shows a `.qn-tag`;
  the reply **restates the question** then answers (`**Q2:** …question… / …answer…`).
- Deep link `?q=N` opens the page and immediately submits `Qn`, then clears the param from the URL.

### Human joins
- When the owner posts from admin, it appears as a **separate** `.msg--human` bubble: the owner's
  photo with a **yellow ring**, a faint **yellow tint** background, a soft **glow**, and the label
  "`OWNER_NAME` — live". The Avatar does not respond to it.
- The page **polls** every 10s for the human's async messages, backing off to every 60s after 5
  minutes of no activity. (Polling is only for picking up human messages; the Avatar reply itself
  streams.)

### Guardrails (visible)
- Message > 20,000 chars is truncated server-side (a note is appended) before storing/sending.
- > 20 messages/min on one conversation → HTTP 429 **before** any LLM call; show a friendly
  "you're sending messages too quickly" line in the thread.

### Responsive
- Single column, `max-width: var(--maxw-chat)`, composer docked at the bottom. The brand subtitle
  and footer link labels hide on narrow screens.

---

## Admin Dashboard (`/admin`)

### Auth
- `POST /admin/login` with `ADMIN_PASSWORD` → signed httpOnly session cookie guarding all
  `/admin/*` APIs. The login screen is a single centered `.card` with a `.field` (password) and a
  `.btn--primary` ("Unlock", `#i-lock`).

### Inbox (sidebar)
- Conversations as an email-style list, **most recent on top**. Each `.convo-item` shows the
  visitor's initials avatar, name/initials, timestamp, and a one-line preview.
- **Unread** (`.is-unread`): stronger text + an `.unread-dot`.
- **Needs attention** (`.needs-attention`, set when `push_tool` fired): yellow-tinted row + a
  yellow `#i-bell-dot`, shown until the human opens the thread.
- **Active** (`.is-active`): a 3px blue selection bar on the left. *(This is a selection
  indicator — the only sanctioned left bar; content panels never get one.)*

### Thread (main panel)
- Opening a conversation shows the full interaction (same bubble orientation as the visitor sees)
  and **scrolls to the latest message**.
- Opening marks every row read, clears `needs_attention`, and returns the updated rows — one
  single Supabase round-trip (PostgREST "update … returning").
- The composer posts **as the owner** ("Reply as `OWNER_NAME`"); the message lands as a
  `.msg--human` bubble.

### Keyboard
- **↑ / ↓** move between conversations. **Enter** sends. **Shift+Enter** newline. Hints render as
  `.kbd` chips under the composer.

### Responsive (master/detail)
- ≤ 860px: the inbox fills the screen. Tapping a conversation opens its thread (scrolled to
  latest) with a **back** control (`#i-back`) to return. Desktop side-by-side layout is unchanged.

---

## States matrix

| State | Visitor | Admin |
|---|---|---|
| Empty | Intro + example chips; composer focused | Inbox list; no thread selected |
| Loading thread | Skeleton / spinner | Skeleton rows |
| Streaming reply | `.tool-line` (mono) → bubble fills; `.typing` | Read-only; new rows arrive on poll |
| Instant `Qn` | `.qn-tag`; reply restates the question | Shows as a normal visitor turn |
| Tool: faq | `.tool-line` (cyan) | same, in history |
| Tool: push | `.tool-line--push` (yellow) + "notified `OWNER_NAME`" | row flips to needs-attention |
| Human joins | `.msg--human` (ring + tint + glow), "— live" | composer posts as owner |
| Needs attention | — | yellow row + `bell-dot` until opened |
| Unread | — | stronger text + unread dot |
| Read | — | row normal; `status-dot--live` "read" badge |
| Rate limited (429) | Friendly "sending too quickly" line | — |
| Truncated input | Note appended to stored/echoed message | visible in history |
| Error / offline | Inline retry affordance | toast / inline notice |
| Mobile | Single column, docked composer | Master/detail: inbox → thread → back |
| Light theme | Full peer of dark | Full peer of dark |
