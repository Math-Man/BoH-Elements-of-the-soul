#!/usr/bin/env python3
"""Convert square aspect icons into circular badges.

The artwork is concentric rings, so the square crop cuts the outer ring away at
the edge midpoints while leaving it intact in the corners: a square's corners sit
at radius 181 where its edges sit at 128. Since colour at a given radius barely
varies with angle, the missing band can be rebuilt by sampling the same radius at
an angle where pixels survive.
"""

import argparse
import pathlib

import numpy as np
from PIL import Image

CANVAS = 336
RADIUS = 162.0
JITTER_DEG = 4.0
SEED = 20260731


def sample_bilinear(src, dx, dy):
    """Sample src at centre-relative coordinates."""
    n = src.shape[0]
    half = (n - 1) / 2
    x = np.clip(dx + half, 0, n - 1.001)
    y = np.clip(dy + half, 0, n - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    return (src[y0, x0] * (1 - fx) * (1 - fy)
            + src[y0, x0 + 1] * fx * (1 - fy)
            + src[y0 + 1, x0] * (1 - fx) * fy
            + src[y0 + 1, x0 + 1] * fx * fy)


def circularize(src, canvas=CANVAS, radius=RADIUS, jitter_deg=JITTER_DEG, seed=SEED):
    """src extended outward and masked to a disc. Returns RGBA."""
    half = (src.shape[0] - 1) / 2
    if radius > np.hypot(half, half):
        raise ValueError(f"radius {radius} exceeds the source's corner radius "
                         f"{np.hypot(half, half):.1f}; nothing to sample from")

    centre = (canvas - 1) / 2
    yy, xx = np.mgrid[0:canvas, 0:canvas].astype(np.float32)
    dy, dx = yy - centre, xx - centre
    r = np.hypot(dx, dy)

    inside = (np.abs(dx) <= half) & (np.abs(dy) <= half)
    fill = ~inside & (r <= radius + 2)

    out = np.zeros((canvas, canvas, 3), np.float32)
    out[inside] = sample_bilinear(src, dx[inside], dy[inside])

    # Angles still inside the square span [lo, 90-lo] within each quadrant.
    with np.errstate(invalid="ignore", divide="ignore"):
        lo = np.degrees(np.arccos(np.clip(half / np.maximum(r, 1e-6), -1, 1)))
    lo = np.where(r <= half, 0.0, lo)
    hi = 90.0 - lo

    # Clamping into the quadrant's own wedge keeps the two-tone split intact;
    # the jitter stops one angular line of pixels stretching into radial streaks.
    deg = np.degrees(np.arctan2(dy, dx)) % 360.0
    quadrant = np.floor(deg / 90.0) * 90.0
    local = np.clip(deg - quadrant, lo, hi)
    local += np.random.default_rng(seed).normal(0, jitter_deg, local.shape)
    theta = np.radians(quadrant + np.clip(local, lo, hi))

    out[fill] = sample_bilinear(src, (r * np.cos(theta))[fill], (r * np.sin(theta))[fill])

    alpha = np.clip(radius + 0.5 - r, 0, 1) * 255.0
    return np.concatenate([np.clip(out, 0, 255), alpha[..., None]], axis=2).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src_dir", type=pathlib.Path)
    ap.add_argument("out_dir", type=pathlib.Path)
    ap.add_argument("--radius", type=float, default=RADIUS,
                    help=f"disc radius in source pixels (default {RADIUS:g})")
    ap.add_argument("--canvas", type=int, default=CANVAS,
                    help=f"output canvas size (default {CANVAS})")
    ap.add_argument("--jitter", type=float, default=JITTER_DEG,
                    help=f"angular jitter in degrees (default {JITTER_DEG:g})")
    args = ap.parse_args()

    paths = sorted(p for p in args.src_dir.iterdir()
                   if p.suffix.lower() in {".webp", ".png", ".jpg", ".jpeg"})
    if not paths:
        raise SystemExit(f"no images found in {args.src_dir}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for p in paths:
        src = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
        if src.shape[0] != src.shape[1]:
            print(f"  skip {p.name}: not square ({src.shape[1]}x{src.shape[0]})")
            continue
        rgba = circularize(src, args.canvas, args.radius, args.jitter)
        dest = args.out_dir / f"{p.stem}.png"
        Image.fromarray(rgba, "RGBA").save(dest, optimize=True)
        print(f"  {p.name} -> {dest.name}")

    print(f"\n{len(paths)} icons -> {args.out_dir}")


if __name__ == "__main__":
    main()
