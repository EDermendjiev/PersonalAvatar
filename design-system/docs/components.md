# Components reference

Every class ships in `components.css` and depends on `tokens.css`. The mockups are composed
entirely from these. Sizes/colors below reference tokens — see `tokens.css` for values.

---

## Icons

```html
<svg class="icon"><use href="icons.svg#i-send"/></svg>
```

- `.icon` (1.25em), `.icon--sm` (1em), `.icon--lg` (1.5em). Inherits `currentColor`.
- Sprite ids: `i-send i-reset i-sun i-moon i-back i-chevron-right i-chevron-down i-check
  i-check-check i-bell i-bell-dot i-user i-bot i-cpu i-sparkles i-arrow-ur i-link i-linkedin
  i-youtube i-mail i-search i-x i-menu i-lock i-message i-zap i-dot i-copy i-keyboard i-radio
  i-arrow-keys`.

## Buttons

| Class | Use |
|---|---|
| `.btn` | Base (secondary look). 44px tall. |
| `.btn--primary` | The **one purple action** (submit/send). |
| `.btn--ghost` | Transparent; toolbar / icon actions. |
| `.btn--icon` | Square 44px; pair with `.btn--sm` for 36px. |
| `.btn--sm` | Compact 36px. |

Hover lightens the surface; `:active` nudges 1px. Focus shows a blue outline.

## Fields & composer

- `.field` — input/textarea base. `textarea.field` auto-pads. Focus = blue border + soft ring.
- `.field-label` — block label.
- `.name-field` — compact pill name input for the visitor header.
- `.composer` — the dock: `.composer__input` (auto-sizing textarea) + `.composer__send` (purple,
  44px). `.composer__hint` for the "Enter to send" line.

## Keep-chat switch

```html
<label class="switch">
  <input type="checkbox" checked>
  <span class="switch__track"></span>
  <span class="switch__label">Keep chat</span>
</label>
```
On = blue track, knob slides right.

## Badges & status

- `.badge` + `.badge--blue` / `--cyan` / `--yellow` (role-tinted). Non-wrapping.
- `.status-dot` + `.status-dot--live` (green, haloed).
- `.qn-tag` — the mono `Qn` instant-answer pill (cyan).
- `.prompt-chip` — clickable example prompt on the intro screen.

## Avatars

- `.avatar` (40px round) + `.avatar--sm` (30) / `.avatar--lg` (56).
- `.avatar--visitor` — blue initials chip (no image).
- `.avatar--twin` — cyan ring; holds `avatar-robot-round.png`.
- `.avatar--owner` — **yellow ring + glow**; holds `avatar-human.png`. Marks the human.

## Message bubbles

```html
<div class="msg msg--avatar">
  <div class="avatar avatar--sm avatar--twin"><img src="assets/avatar-robot-round.png" alt="Avatar"></div>
  <div class="msg__col">
    <div class="msg__meta"><span class="msg__name">Avatar</span><span class="msg__time">14:05</span></div>
    <div class="msg__bubble">…markdown-rendered content…</div>
  </div>
</div>
```

| Modifier | Role | Treatment |
|---|---|---|
| `.msg--visitor` | visitor | right-aligned, blue tint, bottom-right corner squared |
| `.msg--avatar` | twin | left-aligned, cyan name, bottom-left corner squared |
| `.msg--human` | owner | left-aligned, **yellow ring + tint + glow**, `.live-tag` "live" |

Bubbles are asymmetric (one corner squared toward the avatar) — deliberately not generic pills.
No left-edge accent bars. `.msg__bubble a` underlines links.

## Tool-status lines

- `.tool-line` — small mono, dashed border, cyan icon (default / faq).
- `.tool-line--push` — yellow icon (the human was notified).
- `.tool-line--done` — green icon.
- `.typing` — three-dot indicator for "Avatar is composing".

## Inbox rows (admin)

```html
<div class="convo-item is-unread needs-attention">
  <div class="avatar avatar--sm avatar--visitor">EK</div>
  <div class="convo-item__main">
    <div class="convo-item__top"><span class="convo-item__name">EK</span><span class="convo-item__time">14:08</span></div>
    <div class="convo-item__preview">…last message…</div>
  </div>
  <div class="convo-item__flags"><span class="attn-flag"><svg class="icon icon--sm"><use href="icons.svg#i-bell-dot"/></svg></span></div>
</div>
```

| State class | Meaning |
|---|---|
| `.is-active` | selected — 3px blue selection bar (sanctioned) |
| `.is-unread` | stronger text; pair with `.unread-dot` in flags |
| `.needs-attention` | yellow-tinted row; pair with `.attn-flag` + `#i-bell-dot` |

## Surfaces & misc

- `.card` — bordered surface container.
- `.divider` — 1px hairline rule.
- `.has-grid` — applies the canvas grid texture (`--grid-mark`) to any element.
- `.theme-toggle` — wraps sun/moon `<use>`s; the active glyph is shown per `[data-theme]`
  (`.i-sun-show` / `.i-moon-show`).
