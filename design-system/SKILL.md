# SKILL — Build the Avatar front-end from this design system

Use this when turning the design system into the real product UI (vanilla TypeScript + Vite, per
`SPEC.md`). This is the **appearance** brief; `SPEC.md` owns behaviour.

## Setup

1. Copy into `frontend/`: `tokens.css`, `components.css`, `icons.svg`, `assets/`.
2. Put them under e.g. `frontend/src/styles/` and `frontend/public/`.
3. Load order, always: **`tokens.css` → `components.css` → page-specific CSS**.
4. Fonts (Newsreader, Hanken Grotesk, JetBrains Mono) are `@import`ed by `tokens.css`. If you
   prefer `<link>` tags for performance, mirror the same families/weights.
5. Set the initial theme before first paint to avoid a flash:
   ```html
   <script>document.documentElement.setAttribute('data-theme',
     localStorage.getItem('avatar-theme') || 'dark');</script>
   ```

## The two screens

Compose from component classes; lift structure from `mockups/Visitor Chat.html` and
`mockups/Admin Dashboard.html`. Those mockups are the **tie-breaker** for any ambiguity.

- **Visitor Chat (`/`)** — header (brand + name field + Keep-chat switch + reset + theme),
  scrollable thread of `.msg` bubbles, sticky `.composer` dock, footer links. Intro state shows
  `.prompt-chip` examples. See `docs/ux-flows.md` §Visitor.
- **Admin Dashboard (`/admin`)** — `var(--sidebar-w)` inbox of `.convo-item` rows + main `.panel`
  with thread and a "reply as owner" composer. Desktop side-by-side; mobile master/detail. See
  `docs/ux-flows.md` §Admin.

## Hard rules (appearance)

- **Roles map to color, always.** visitor → blue, avatar → cyan, human → yellow. Use the
  `--role-*` tokens; never restyle a bubble off-palette.
- **Purple is for primary actions only** (`.btn--primary`, `.composer__send`). Never for chrome,
  text, or decoration.
- **Yellow is for the human only** — the owner's bubble, the needs-attention inbox state, the
  "live" tag. Don't use it for generic accents.
- **No gradients in chrome. No purple wash. No left-edge accent bars on content.** (The active
  inbox row's 3px bar is a *selection indicator* and is allowed — follow the mockups.)
- **No emoji.** Icons come from `icons.svg`.
- Derive every color from `tokens.css`. An unresolved `var()` is a bug.

## Acceptance checklist

- [ ] Dark is the default; light is a full peer; toggle persists in `localStorage['avatar-theme']`.
- [ ] All three bubble roles render with correct color + the human bubble has ring + tint + glow.
- [ ] The composer takes focus on load and **regains focus after sending** (use `{preventScroll:true}`).
- [ ] Tool use renders as small mono `.tool-line` while streaming; `push_tool` line uses yellow.
- [ ] `Qn` shows the `.qn-tag`; the reply restates the question (per SPEC).
- [ ] Example-prompt chips submit immediately on click.
- [ ] Admin inbox shows unread (dot + stronger text), needs-attention (yellow row + bell-dot),
      and active (selection bar) states; arrow keys move, Enter sends, Shift+Enter newlines.
- [ ] Both screens work at 360px wide and on desktop; admin collapses to master/detail on mobile.
- [ ] No emoji; no gradients in chrome; no unresolved `var()`; icons inherit `currentColor`.
- [ ] Owner name is read from `OWNER_NAME` everywhere it appears — never hardcoded.

## Where things live

| Need | Look in |
|---|---|
| A token name / value | `tokens.css` (and the Color/Type sections of the doc) |
| A component's classes | `docs/components.md` + `components.css` |
| Exact screen markup | `mockups/*.html` |
| Interaction contract / states | `docs/ux-flows.md` |
| Regenerating avatars | `docs/avatar-generation.md` |
