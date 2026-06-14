# Avatar — Design System

The complete visual and interaction system for **Avatar**, the digital-twin web app for
**Emil Dermendzhiev**. It pairs with `SPEC.md` at the repo root.

> **The split is explicit.** `SPEC.md` governs **behaviour and the backend**.
> This `design-system/` governs **look and feel**. When the two disagree, SPEC wins on
> behaviour; the design system wins on appearance.

Open **`Avatar Design System.html`** first — it's the navigable system and it dogfoods its own tokens.

---

## Design language in one breath

Dark-first, navy-tinted surfaces. Editorial serif **Newsreader** (display + message bodies) +
crisp grotesque **Hanken Grotesk** (UI) + **JetBrains Mono** (technical layer). **Blue-led**
identity, with **yellow as the "spark" reserved for the human-in-the-loop** and **purple locked
to primary actions only**. No gradients in chrome, no purple wash, no left-edge accent bars on
content, no emoji. This is deliberately *not* a generic chatbot.

**Role colors are the load-bearing system:** `visitor = blue`, `avatar (the twin) = cyan`,
`human (the owner) = yellow`.

---

## Contents

| File / folder | Purpose |
|---|---|
| `Avatar Design System.html` | The navigable design-system document. **Open this first.** |
| `SKILL.md` | Front-end build brief + acceptance checklist. |
| `tokens.css` | **Single source of truth** — palette, type, spacing, radii, motion, dark + light themes. |
| `components.css` | Build-ready component classes. Depends on `tokens.css`. |
| `doc.css` | Styles for the doc page only — **not product code**. |
| `icons.svg` | Stroke icon sprite. Used as `<use href="icons.svg#i-…">`, inherits `currentColor`. |
| `assets/` | `avatar-human.png`, `avatar-robot.png`, `avatar-robot-round.png`. |
| `mockups/` | `Visitor Chat.html`, `Admin Dashboard.html` — the literal build targets / tie-breakers. |
| `docs/ux-flows.md` | Every interaction contract + a states matrix to design and test against. |
| `docs/components.md` | Component-by-component class reference. |
| `docs/avatar-generation.md` | Recipe to produce the twin images from the owner's photo. |

---

## How to use it in the build

The frontend is vanilla TypeScript + Vite (per SPEC). 

1. Copy `tokens.css`, `components.css`, `icons.svg` and `assets/` into the frontend.
2. Load order: **`tokens.css` → `components.css` → page CSS**.
3. Import the Google Fonts (Newsreader, Hanken Grotesk, JetBrains Mono) — already `@import`ed at
   the top of `tokens.css`.
4. Build the two screens by composing the component classes and lifting the markup from the
   mockups. The mockups are the tie-breaker for any ambiguity.
5. Default theme is **dark**, persisted in `localStorage['avatar-theme']` and applied via
   `[data-theme]` on `<html>`.
6. **Derive every color from tokens. Never invent one.**

> **Note on the inlined sprite.** The shipped mockups inline `icons.svg` at the top of `<body>`
> (and reference `#i-…`) so they render as standalone files. In the real Vite build, load the
> external `icons.svg` once and keep the `<use href="icons.svg#i-…">` form.

---

## Owner-specific regeneration

These assets, copy, and identity are built for **Emil Dermendzhiev**. If a different owner stands
up their own site, regenerate end to end: the avatar images from their own `knowledge/pic.jpg`
(see `docs/avatar-generation.md`), the human photo, the brand subtitle, and any owner-specific
copy. The owner's name comes from the `OWNER_NAME` env var and is shown throughout the UI
(including the human bubble, e.g. "Emil Dermendzhiev — live"); it must always be read from config
and never hardcoded.
