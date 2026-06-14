#!/usr/bin/env python3
"""Generate the digital-twin avatar images from the owner's photo.

Implements the deterministic recipe in design-system/docs/avatar-generation.md:
a cyan "scan" duotone grade plus a HUD overlay, with no AI model. Produces three
512x512 PNGs from knowledge/pic.png (a head-and-shoulders portrait):

  avatar-human.png        clean square crop of the real photo (the human/owner)
  avatar-robot.png        square scan, HUD-framed (square/identity contexts)
  avatar-robot-round.png  round twin, tuned for circular chat avatars (the Avatar)

Run:  uv run --with pillow --with numpy python scripts/gen_avatars.py
Outputs are written to design-system/assets/ and frontend/public/assets/.

The twin is the SAME photo, scanned: recognizably the owner, visibly synthetic.
Cyan only (the --role-avatar color); navy #04101e backdrop; never yellow.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "knowledge" / "pic.png"
OUT_DIRS = [ROOT / "design-system" / "assets", ROOT / "frontend" / "public" / "assets"]
SIZE = 512

# Duotone ramp stops (luminance -> color), per the recipe.
RAMP = [
    (0.00, (0x04, 0x10, 0x1e)),
    (0.42, (0x0e, 0x40, 0x60)),
    (0.66, (0x21, 0x96, 0xb6)),
    (0.85, (0x40, 0xc8, 0xe0)),
    (1.00, (0xce, 0xf4, 0xff)),
]
CYAN = (0x40, 0xc8, 0xe0)
NAVY = (0x04, 0x10, 0x1e)
BLEND = 0.62  # mix toward the scan; lower = subtler, higher = more synthetic


def build_ramp_lut() -> np.ndarray:
    """256-entry RGB lookup from the ramp stops."""
    lut = np.zeros((256, 3), dtype=np.float64)
    stops = RAMP
    for i in range(256):
        t = i / 255.0
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                lut[i] = [c0[k] + (c1[k] - c0[k]) * f for k in range(3)]
                break
        else:
            lut[i] = stops[-1][1]
    return lut


def duotone(rgb: np.ndarray, blend: float = BLEND) -> np.ndarray:
    """Apply the cyan scan grade to an HxWx3 float array (0..255)."""
    lum = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]) / 255.0
    lum = np.clip((lum - 0.5) * 1.12 + 0.5, 0.0, 1.0)
    idx = np.clip((lum * 255).astype(int), 0, 255)
    lut = build_ramp_lut()
    scan = lut[idx]
    return rgb * (1.0 - blend) + scan * blend


def crop_resize(src: Image.Image, sx: int, sy: int, side: int) -> Image.Image:
    return src.crop((sx, sy, sx + side, sy + side)).resize((SIZE, SIZE), Image.LANCZOS)


def vignette(size: int, strength: float = 0.55) -> np.ndarray:
    """Radial darken-to-navy mask, returns HxW alpha 0..1 (edge=strength)."""
    yy, xx = np.mgrid[0:size, 0:size]
    cx = cy = size / 2
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (size / 2)
    return np.clip((d - 0.55) / 0.45, 0, 1) * strength


def apply_vignette(arr: np.ndarray) -> np.ndarray:
    v = vignette(arr.shape[0])[..., None]
    navy = np.array(NAVY, dtype=np.float64)
    return arr * (1 - v) + navy * v


def overlay_layer() -> Image.Image:
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))


def draw_grid_scanlines(img: Image.Image) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    grid = (*CYAN, 13)        # ~5% alpha
    scan = (0, 0, 0, 13)
    for x in range(0, SIZE, 32):
        d.line([(x, 0), (x, SIZE)], fill=grid, width=1)
    for y in range(0, SIZE, 32):
        d.line([(0, y), (SIZE, y)], fill=grid, width=1)
    for y in range(0, SIZE, 3):   # scanlines
        d.line([(0, y), (SIZE, y)], fill=scan, width=1)


def square_hud() -> Image.Image:
    layer = overlay_layer()
    d = ImageDraw.Draw(layer, "RGBA")
    draw_grid_scanlines(layer)
    m, blen = 18, 60
    bracket = (*CYAN, 235)
    # corner brackets
    for (cx, cy, dx, dy) in [(m, m, 1, 1), (SIZE - m, m, -1, 1),
                             (m, SIZE - m, 1, -1), (SIZE - m, SIZE - m, -1, -1)]:
        d.line([(cx, cy), (cx + dx * blen, cy)], fill=bracket, width=2)
        d.line([(cx, cy), (cx, cy + dy * blen)], fill=bracket, width=2)
    # inner frame (40% opacity)
    d.rectangle([m + 8, m + 8, SIZE - m - 8, SIZE - m - 8], outline=(*CYAN, 102), width=1)
    # targeting reticle around the head
    rx, ry, rr = SIZE // 2, int(SIZE * 0.40), 150
    d.ellipse([rx - rr, ry - rr, rx + rr, ry + rr], outline=(*CYAN, 120), width=2)
    for k in range(12):
        a = math.radians(k * 30)
        x0, y0 = rx + math.cos(a) * (rr - 8), ry + math.sin(a) * (rr - 8)
        x1, y1 = rx + math.cos(a) * (rr + 8), ry + math.sin(a) * (rr + 8)
        d.line([(x0, y0), (x1, y1)], fill=(*CYAN, 160), width=2)
    # data ticks bottom-left
    for i in range(5):
        y = SIZE - 40 + i * 6
        d.line([(34, y), (34 + (8 + i * 9), y)], fill=(*CYAN, 150), width=2)
    # circuit node top-right
    d.ellipse([SIZE - 54, 40, SIZE - 44, 50], outline=(*CYAN, 200), width=2)
    d.line([(SIZE - 49, 50), (SIZE - 49, 70)], fill=(*CYAN, 160), width=2)
    return layer


def round_hud() -> Image.Image:
    layer = overlay_layer()
    d = ImageDraw.Draw(layer, "RGBA")
    cx = cy = SIZE / 2
    r = SIZE / 2 - 2
    # edge ring
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*CYAN, 235), width=3)
    # tick dial every 15deg, longer at 90
    for deg in range(0, 360, 15):
        a = math.radians(deg)
        long = deg % 90 == 0
        t = 16 if long else 9
        x0, y0 = cx + math.cos(a) * (r - t), cy + math.sin(a) * (r - t)
        x1, y1 = cx + math.cos(a) * (r - 3), cy + math.sin(a) * (r - 3)
        d.line([(x0, y0), (x1, y1)], fill=(*CYAN, 200 if long else 130), width=2 if long else 1)
    return layer


def circle_mask() -> Image.Image:
    m = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(m).ellipse([0, 0, SIZE, SIZE], fill=255)
    return m


def save(img: Image.Image, name: str) -> None:
    for d in OUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        img.save(d / name)
    print(f"wrote {name}")


def main() -> None:
    src = Image.open(SRC).convert("RGB")
    print(f"source {SRC} {src.size}")

    # 1. Human: clean square crop, no scan.
    human = crop_resize(src, 96, 120, 1600).convert("RGBA")
    save(human, "avatar-human.png")

    # 2. Square robot: scan + vignette + HUD.
    base_sq = np.asarray(crop_resize(src, 96, 120, 1600), dtype=np.float64)
    graded = apply_vignette(duotone(base_sq))
    sq = Image.fromarray(np.clip(graded, 0, 255).astype(np.uint8)).convert("RGBA")
    sq.alpha_composite(square_hud())
    save(sq, "avatar-robot.png")

    # 3. Round robot: tighter crop, scan, clipped to circle, ring dial.
    base_rd = np.asarray(crop_resize(src, 246, 210, 1320), dtype=np.float64)
    graded_rd = duotone(base_rd)
    rd = Image.fromarray(np.clip(graded_rd, 0, 255).astype(np.uint8)).convert("RGBA")
    rd.alpha_composite(round_hud())
    rd.putalpha(circle_mask())
    save(rd, "avatar-robot-round.png")


if __name__ == "__main__":
    main()
