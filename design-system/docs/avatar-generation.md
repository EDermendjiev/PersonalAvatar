# Avatar generation — the digital twin images

Three images drive the identity. All three live in `assets/` and are the **source of truth** —
don't re-derive them at build time, just ship them.

| File | What | Where it's used |
|---|---|---|
| `avatar-human.png` | Clean square crop of the owner's real photo | the **human** (owner) bubble + admin |
| `avatar-robot.png` | Square "scan" of the same photo, HUD-framed | square/identity contexts, the doc |
| `avatar-robot-round.png` | Round twin, tuned for circular chat avatars | the **Avatar** (twin) bubble |

The twin is the **same photo, scanned** — recognizably the owner, visibly synthetic. We do *not*
swap in a generic robot; the point is that it's *their* twin.

---

## The recipe (image-processing, reproducible)

Input: `knowledge/pic.png` (or `pic.jpg`) — a head-and-shoulders portrait. Output: 512×512 PNGs.
This is exactly how the shipped assets were produced; it's deterministic and needs no model.

### 1. Crop
- **Human / square robot:** centre-weighted square covering head + shoulders.
  For a 1792×2400 source: `sx=96, sy=120, side=1600`.
- **Round robot:** tighter, face-centred square so the face survives the circular clip.
  `sx=246, sy=210, side=1320`.
Adjust per source so the eyes sit ~38–42% down the frame.

### 2. Cyan duotone grade (the "scan")
Map each pixel's luminance through a navy→teal→cyan→near-white ramp, then blend back toward the
original so it stays recognizable (**balanced intensity** = blend `0.62`).

```
lum  = 0.299R + 0.587G + 0.114B           // 0..1
lum  = clamp((lum-0.5)*1.12 + 0.5)        // gentle contrast
ramp stops:  0.00 #04101e · 0.42 #0e4060 · 0.66 #2196b6 · 0.85 #40c8e0 · 1.00 #cef4ff
out  = mix(original, ramp(lum), 0.62)
```

Lower the blend (≈0.45) for a subtler "clearly the owner" look; raise it (≈0.8) for a stronger
synthetic read.

### 3. HUD overlay (square)
- A cool radial vignette to settle the edges into navy.
- Faint **grid** (cyan, ~5% alpha, 32px) + horizontal **scanlines** (~5% alpha, every 3px).
- **Corner brackets** (cyan, 2px) at all four corners + a thin 40%-opacity inner frame.
- A **targeting reticle** ring around the head with 12 tick marks; small cyan data ticks
  bottom-left and a tiny circuit node top-right.

### 4. HUD overlay (round)
- Same grade + scanlines, clipped to a circle (transparent outside).
- A 3px cyan **ring** at the edge with a tick **dial** (every 15°, longer ticks at 90°) — reads as
  a HUD instrument when shown as a small circular avatar.

### Palette discipline
The twin is **cyan only** — it is the `--role-avatar` color. Do **not** add yellow to the twin;
yellow belongs exclusively to the human. Navy `#04101e` is the synthetic backdrop.

---

## Regenerating for a different owner

1. Drop the new portrait at `knowledge/pic.jpg`.
2. Re-run the recipe (re-tune the crop so the eyes land ~40% down; keep blend ≈0.62).
3. Overwrite all three files in `assets/` and the human photo wherever it's shipped
   (`frontend/public/`).
4. Update the brand subtitle and any owner-specific copy, and set `OWNER_NAME` in `.env`.

> If you'd rather produce a true generative robot portrait instead of the scan treatment, keep the
> same role rules: cyan-led, navy backdrop, no yellow, and it must still read as *this* person's
> twin (same framing, same recognizable face) — not a stock android.
