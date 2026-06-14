# Frontend test plan

Checklist for the vanilla-TypeScript + Vite frontend (visitor `/` and admin `/admin`). Items are
drawn from the **SKILL.md acceptance checklist**, the **ux-flows.md states matrix**, and the
behaviour contract in **CONTRACT.md §10**. Appearance ties go to `mockups/Visitor Chat.html` and
`mockups/Admin Dashboard.html`; component classes are defined in `design-system/components.css`.

How to run: drive both pages with Playwright (against the dev server or the built `dist/` served by
the backend). Exercise dark + light, desktop + 360px mobile, and capture screenshots for each major
state. Delete all screenshots after the run (per SPEC testing rules). SPEC traceability is noted in
each section header.

---

## 1. Theme (SKILL acceptance; ux-flows "Light theme"; CONTRACT §10)

- [x] Dark is the default theme on first load (no stored preference).
- [x] Theme is set **before first paint** (no flash): the pre-paint script sets `data-theme` from `localStorage['avatar-theme']` or `dark`.
- [x] The theme toggle (sun/moon, `.theme-toggle` with `#i-sun`/`#i-moon`) switches dark↔light.
- [x] The chosen theme persists in `localStorage['avatar-theme']` across reloads.
- [x] Light mode is a full peer: both screens are legible and on-palette in light (no unstyled regions).
- [x] No unresolved `var()` in either theme (computed styles resolve to real token values).

## 2. Branding & owner name from config (SPEC Q&A #11; CONTRACT §10)

- [x] Visitor page fetches `GET /api/config` and renders `owner_name` in the header/subtitle, the page `<title>`, and the twin's name — never hardcoded.
- [x] Admin page reads `owner_name` from `GET /api/admin/me` and shows it (e.g. "Reply as {OWNER_NAME}").
- [x] No literal "Emil Dermendzhiev" or other owner name appears in shipped frontend source.

## 3. Visitor — message bubble roles (SKILL acceptance; ux-flows roles table)

- [x] Visitor bubble: `.msg--visitor`, right-aligned, **blue** tint, `.avatar--visitor` initials chip.
- [x] Avatar bubble: `.msg--avatar`, left-aligned, **cyan** name, `.avatar--twin` with `avatar-robot-round.png`.
- [x] Human bubble: `.msg--human`, **yellow ring + tint + glow**, `.avatar--owner` with `avatar-human.png`, `.live-tag` "live" and "{OWNER_NAME} — live" label.
- [x] Roles map to color consistently; no bubble is restyled off the `--role-*` palette.
- [x] Message bodies render markdown via `lib/markdown.ts` (marked + DOMPurify); links underline and are clickable; no raw HTML injection.
- [x] Timestamps render via `formatTime`; initials via `initials()`.

## 4. Visitor — composer focus & keyboard (SPEC focus mandate; SKILL acceptance)

- [x] The composer input takes focus on page load (`focus({preventScroll:true})`).
- [x] After sending (click or Enter), the composer **regains** focus.
- [x] **Enter** submits; **Shift+Enter** inserts a newline (no submit).
- [x] The composer auto-sizes for multi-line input.

## 5. Visitor — intro / empty state & prompt chips (SPEC; SKILL acceptance)

- [x] Empty state shows intro copy + a few `.prompt-chip` example prompts.
- [x] Clicking a `.prompt-chip` **submits it immediately**.
- [x] After the first exchange the intro state is replaced by the thread.

## 6. Visitor — SSE streaming & tool lines (SPEC Q&A #9; ux-flows streaming row; SKILL acceptance)

- [x] On send, a `.typing` indicator may show before the first token.
- [x] The reply streams token-by-token into the `.msg__bubble`.
- [x] `faq_tool` use renders as a small mono `.tool-line` (cyan icon), e.g. `faq_tool · "…"`.
- [x] `push_tool` use renders as `.tool-line--push` (yellow bell) and the bubble states the owner was notified.
- [x] Tool lines use JetBrains Mono and the dashed-border treatment from `components.css`.

## 7. Visitor — Qn instant answers & deep link (SPEC; ux-flows; SKILL acceptance)

- [x] A bare `Qn` (e.g. `Q2`) shows the `.qn-tag` (cyan mono pill) on the **visitor** turn.
- [x] The reply **restates the question** then answers (`**Q2:** …question… / …answer…`).
- [x] Deep link `?q=N` (e.g. `/?q=2`) auto-submits `Qn` on load.
- [x] After auto-submit, the `?q` param is stripped from the URL via `history.replaceState`.

## 8. Visitor — Keep chat / reset / persistence (SPEC; CONTRACT §10)

- [x] A `conversation_id` UUID is generated via `crypto.randomUUID`.
- [x] "Keep chat" switch (`.switch`) defaults **on**; the id persists in cookie `avatar_cid` (SameSite=Lax).
- [x] On reload with Keep chat on, the prior thread is restored via `GET /api/conversation/{id}`.
- [x] Turning Keep chat **off** stops cookie persistence (a reload starts fresh).
- [x] **Reset** (`.btn--icon`, `#i-reset`) clears the thread and assigns a fresh `conversation_id`.
- [x] The optional name field seeds the visitor's `.avatar--visitor` initials chip.

## 9. Visitor — polling for human messages (SPEC polling; CONTRACT §10)

- [x] The page polls `GET /api/conversation/{id}` every **10s**.
- [x] Polling backs off to every **60s** after 5 minutes of no activity.
- [x] A human reply (posted from admin) appears as a `.msg--human` bubble on the next poll without a page reload.
- [x] Polling only fetches human/async updates; the Avatar reply itself arrives via SSE.

## 10. Visitor — guardrail UX (SPEC Q&A #12; ux-flows guardrails)

- [x] A 429 response shows a friendly inline "you're sending messages too quickly" line in the thread (not a crash/blank).
- [x] A truncated input (note appended server-side) renders the appended note in the echoed/stored message.
- [x] An error/offline state shows an inline retry affordance rather than failing silently.

## 11. Visitor — responsive 360px (SKILL acceptance; ux-flows responsive)

- [x] At 360px wide: single column, `max-width: var(--maxw-chat)`, composer docked at bottom.
- [x] The brand subtitle and footer link labels hide on narrow screens.
- [x] No horizontal overflow at 360px; bubbles wrap correctly.

## 12. Visitor — footer links (CONTRACT §10)

- [x] LinkedIn link → `https://www.linkedin.com/in/emildermendzhiev-7a249a244`.
- [x] Website link → `https://epsystems.org`.
- [x] Email link → `emildermendjiev9@gmail.com` (mailto).
- [x] No YouTube link is invented (omitted or reuses the website URL).
- [x] Footer icons come from `icons.svg` (`#i-linkedin`, `#i-link`, `#i-mail`); no emoji.

## 13. Admin — login (SPEC admin auth; ux-flows admin auth)

- [x] `/admin` shows a single centered `.card` login with a password `.field` and a `.btn--primary` ("Unlock", `#i-lock`).
- [x] Correct password unlocks → inbox + thread layout appears.
- [x] Wrong password shows an inline error and stays on the login screen.
- [x] On load the page calls `GET /api/admin/me` to decide whether to show login or the dashboard.

## 14. Admin — inbox states (SPEC; ux-flows states matrix; SKILL acceptance)

- [x] Conversations list **most-recent on top**, each `.convo-item` with initials avatar, name/initials, timestamp, one-line preview.
- [x] **Unread** rows show `.is-unread` (stronger text) + an `.unread-dot` flag.
- [x] **Needs-attention** rows show `.needs-attention` (yellow-tinted row) + `.attn-flag` with `#i-bell-dot`.
- [x] **Active** row shows `.is-active` with the 3px blue selection bar (the sanctioned left bar).
- [x] Opening a thread clears its unread + needs-attention state in the inbox (after the read-marking call).

## 15. Admin — thread & reply as owner (SPEC; ux-flows admin thread)

- [x] Selecting a conversation calls `GET /api/admin/conversation/{id}` (marks read) and renders the full thread.
- [x] The thread **scrolls to the latest message** on open.
- [x] The composer label reads "Reply as {OWNER_NAME}"; posting calls the admin message endpoint and renders a new `.msg--human` bubble.
- [x] The open thread polls (~10s) for new visitor/avatar rows; the inbox refreshes periodically.

## 16. Admin — keyboard navigation (SPEC arrow keys/Enter; SKILL acceptance)

- [x] **↑ / ↓** move the selection between conversations in the inbox.
- [x] **Enter** sends the composer message; **Shift+Enter** inserts a newline.
- [x] Keyboard hints render as `.kbd` chips under the composer.

## 17. Admin — responsive master/detail (SPEC mobile admin; ux-flows responsive)

- [x] At ≤860px (test 360px): the inbox fills the screen; no side-by-side panel.
- [x] Tapping a conversation opens its thread (scrolled to latest) full-screen.
- [x] A back control (`#i-back`) returns to the inbox.
- [x] The desktop side-by-side layout (`var(--sidebar-w)` inbox + `.panel`) is unchanged above the breakpoint.

## 18. Cross-cutting appearance rules (SKILL hard rules)

- [x] **No emoji** anywhere; all symbols come from `icons.svg` and inherit `currentColor`.
- [x] **No gradients in chrome**; **no purple wash**; purple appears **only** on primary actions (`.btn--primary`, `.composer__send`).
- [x] **Yellow appears only** for the human (owner bubble, needs-attention row, "live" tag).
- [x] **No left-edge accent bars on content** (only the active inbox-row selection bar is allowed).
- [x] CSS load order is `tokens.css` → `components.css` → page CSS on both pages.
- [x] Fonts Newsreader (display), Hanken Grotesk (UI), JetBrains Mono (technical) load and apply.

## 19. Build artifacts (CONTRACT §12 frontend DoD)

- [x] `npm run build` produces `dist/index.html`, `dist/admin.html`, and `dist/assets/**`.
- [x] `public/icons.svg` and `public/assets/avatar-*.png` are present in the build output.
- [x] No console errors on load of either built page (checked via Playwright console capture).

## 20. Screenshot matrix (capture, verify, then delete)

- [x] Visitor empty/intro — dark, desktop.
- [x] Visitor empty/intro — light, desktop.
- [x] Visitor mid-stream with `.tool-line` (faq) — dark.
- [x] Visitor with `push_tool` line + "notified {OWNER_NAME}" — dark.
- [x] Visitor with all three bubble roles incl. `.msg--human` — dark + light.
- [x] Visitor `Qn` instant answer showing `.qn-tag` — dark.
- [x] Visitor at 360px — dark + light.
- [x] Admin login `.card` — dark + light.
- [x] Admin inbox showing unread / needs-attention / active states — dark.
- [x] Admin open thread with owner reply composer — dark + light.
- [x] Admin master/detail at 360px (inbox view and thread view) — dark.
- [x] All screenshots deleted after the run (cleanup).
