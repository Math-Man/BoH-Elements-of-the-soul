#!/usr/bin/env python3
"""Height and normal maps from the circular badges, for Blender brush stamps.

Most of the luminance in these icons is paint rather than form. The vertical
two-tone split would read as a cliff down the middle of the disc, so instead of
converting luminance to height the artwork is modelled as pale ink over a flat
base colour that differs per side. Subtracting that base cancels the split,
because the split is the base.

Ink levels aren't comparable between icons (the rings sit at 0.30 coverage on
most of them but near 0.50 on the bright ones), so each icon is normalised
against its own rings.
"""

import argparse
import pathlib

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, gaussian_filter, label

RING_BANDS = ((93, 100), (124, 131), (153, 160))   # radii, in source pixels
PLAIN_BANDS = ((105, 120), (137, 150))             # ring-free background annuli

RING_HEIGHT = 0.55      # where ring tops land in the normalised height range
COIN_FIELD = 0.35       # disc field height for the coin profile
ENGRAVE_DEPTH = 0.65    # how far ink is cut down for the engraved profile
BEVEL_PX = 5.0          # rim falloff width
INK_BLUR = 0.7          # subtle bevel on ink edges


def ink_coverage(rgb, dx, r, disc):
    """Ink coverage per pixel, with the per-side base colour removed."""
    ink = np.zeros(r.shape, np.float32)
    plain = np.zeros(r.shape, bool)
    for lo, hi in PLAIN_BANDS:
        plain |= (r > lo) & (r < hi)
    plain &= disc

    for side in (dx < 0, dx >= 0):
        m = plain & side
        if m.sum() < 100:
            raise ValueError("not enough background pixels to estimate the base")
        base = np.median(rgb[m], axis=0)
        head = 255.0 - base
        # px = base + a*(255-base), least squares over RGB. Weighting by headroom
        # keeps a near-saturated channel from dominating.
        a = (((rgb - base) * head).sum(2) / (head**2).sum())
        # A per-channel median base and a cross-channel coverage sum don't agree to
        # zero on their own, and the leftover offset resurfaces as height later.
        ink[side] = (a - np.median(a[m]))[side]
    return heal_seam(ink, rgb.mean(2))


def heal_seam(ink, lum, seam_half=2, ref_width=3, flat_rgb=20.0):
    """Flatten the artwork's edge treatment at the two-tone boundary.

    The split carries a bright column on one side and a dark one on the other,
    which becomes a raised ridge beside a groove. It's a colour device, so it
    shouldn't be geometry.
    """
    n = ink.shape[1]
    mid = (n - 1) / 2
    a_lo, a_hi = int(np.floor(mid)) - seam_half, int(np.ceil(mid)) + seam_half
    if a_lo - ref_width < 0 or a_hi + ref_width >= n:
        return ink

    # Tested in RGB, not coverage: a light base leaves little headroom and inflates
    # grain there. Per side, since the split itself is a large step.
    smooth = gaussian_filter(lum, 1.0)
    left = smooth[:, a_lo - ref_width:a_lo + 1]
    right = smooth[:, a_hi:a_hi + ref_width + 1]
    rows = ((left.max(1) - left.min(1)) < flat_rgb) & \
           ((right.max(1) - right.min(1)) < flat_rgb)

    cols = np.arange(a_lo + 1, a_hi)
    t = (cols - a_lo) / (a_hi - a_lo)

    # Uniform references alone aren't enough. A centred glyph gives matching
    # anchors while hiding a stroke between them, and rebuilding that row cuts a
    # band through the design, so check the seam columns against a straight ramp.
    ramp = (smooth[:, a_lo][:, None] * (1 - t)[None, :]
            + smooth[:, a_hi][:, None] * t[None, :])
    dev = np.abs(smooth[:, cols] - ramp).max(1)

    dist = np.abs(np.arange(ink.shape[0]) - mid)
    field_rows = np.zeros(ink.shape[0], bool)
    for lo, hi in PLAIN_BANDS:
        field_rows |= (dist > lo) & (dist < hi)
    limit = max(18.0, 1.6 * np.percentile(dev[field_rows], 95))
    rows &= dev < limit

    out = ink.copy()
    a, b = ink[:, a_lo], ink[:, a_hi]
    out[np.ix_(rows, cols)] = a[rows, None] * (1 - t)[None, :] + b[rows, None] * t[None, :]
    return out


def radial_field(ink, dx, r, disc, skip):
    """Median over angle at each radius: the rings without the grain.

    Decorations are a minority at any given radius and drop out of the median,
    which is what leaves them isolatable afterwards. Also returns which radii the
    result can be trusted at.
    """
    field = np.zeros(r.shape, np.float32)
    trust = np.zeros(r.shape, bool)
    rq = np.rint(r).astype(int)
    rmax = int(rq[disc].max())
    idx = np.arange(rmax + 1)
    for side in (dx < 0, dx >= 0):
        prof = np.full(rmax + 1, np.nan, np.float32)
        for k in range(rmax + 1):
            m = disc & side & (rq == k) & ~skip
            if m.sum() >= 20:
                prof[k] = np.median(ink[m])
        known = ~np.isnan(prof)
        if known.sum() < 10:
            continue
        # A radius the glyph nearly fills has too few samples, and interpolating
        # across a run of those invents a level. Only trust radii near a real one.
        near = np.abs(idx[:, None] - idx[known][None, :]).min(1) <= 2
        prof = np.interp(idx, idx[known], prof[known])
        field[side] = prof[np.clip(rq, 0, rmax)][side]
        trust[side] = near[np.clip(rq, 0, rmax)][side]
    return field, trust


def mirror_grain(ink, dx, r, disc, grain_max=0.08):
    """Mirror the light half's grain onto the flat half, for symmetric texture.

    Isolated against the radial field rather than by high-pass filtering, since a
    Gaussian wide enough to sit under the grain's few-pixel blobs tracks them
    instead of separating them.
    """
    glyph = binary_dilation(ink > 0.75, iterations=2)
    field, trust = radial_field(ink, dx, r, disc, skip=glyph)
    grain = ink - field
    isolated = disc & trust & ~glyph & (np.abs(grain) < grain_max)   # bigger = decoration
    mirrored = np.where(isolated & (dx < 0), grain, 0.0)[:, ::-1]
    out = ink.copy()
    target = isolated & (dx >= 0)
    out[target] += mirrored[target]
    return out


def suppress_grain(ink, dx, r, disc, min_px=30, excess_min=0.04):
    """Remove grain by size rather than by frequency.

    Grain is coherent blobs a few pixels across and the decorations span 15 to 25,
    so component size separates them where amplitude can't: both peak near 8%
    coverage.
    """
    glyph = binary_dilation(ink > 0.75, iterations=2)
    field, trust = radial_field(ink, dx, r, disc, skip=glyph)
    excess = ink - field

    # Both signs, or everything darker than the field gets raised up to it and the
    # ring gaps close.
    lab, _ = label(np.abs(excess) > excess_min)
    sizes = np.bincount(lab.ravel())
    big = np.nonzero(sizes >= min_px)[0]
    keep = np.isin(lab, big[big != 0])

    out = np.where(trust, field + np.where(keep, excess, 0.0), ink)
    out[glyph] = ink[glyph]
    return out


GRAIN = {"asis": lambda ink, dx, r, disc: ink,
         "mirrored": mirror_grain,
         "suppressed": suppress_grain}


def tone_curve(ink, r, disc):
    """Remap ink so background->0, this icon's rings->RING_HEIGHT, white->1."""
    band = np.zeros(r.shape, bool)
    for lo, hi in RING_BANDS:
        band |= (r > lo + 1) & (r < hi - 1)
    ring = float(np.median(ink[band & disc]))
    if not 0.05 < ring < 0.95:
        raise ValueError(f"implausible ring coverage {ring:.3f}")

    x = np.clip(ink, 0.0, 1.0)
    low = x / ring * RING_HEIGHT
    high = RING_HEIGHT + (x - ring) / (1.0 - ring) * (1.0 - RING_HEIGHT)
    return np.where(x <= ring, low, high).astype(np.float32), ring


def profiles(h, r, radius, alpha):
    """The three cross-sections, each masked to the disc."""
    rim = np.clip((radius - r) / BEVEL_PX, 0.0, 1.0)
    rim = rim * rim * (3.0 - 2.0 * rim)          # smoothstep
    disc = rim * alpha
    return {
        "relief": h * disc,
        "coin": (COIN_FIELD + (1.0 - COIN_FIELD) * h) * disc,
        "engraved": (1.0 - ENGRAVE_DEPTH * h) * disc,
    }


def normal_map(h, strength=6.0):
    """Tangent-space normal from height, +Y up (OpenGL)."""
    gy, gx = np.gradient(h.astype(np.float32))
    n = np.stack([-gx * strength, gy * strength, np.ones_like(h)], axis=2)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return (n + 1.0) * 0.5


def save16(arr, path):
    """16-bit grayscale; 8-bit bands visibly once Blender displaces with it."""
    q = np.rint(np.clip(arr, 0.0, 1.0) * 65535.0).astype(np.uint16)
    Image.fromarray(q).save(path)   # uint16 infers I;16


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src_dir", type=pathlib.Path, help="circular RGBA badges")
    ap.add_argument("out_dir", type=pathlib.Path)
    ap.add_argument("--radius", type=float, default=162.0)
    ap.add_argument("--grain", choices=(*GRAIN, "all"), default="all",
                    help="how to treat the light half's grain (default all)")
    ap.add_argument("--no-normals", action="store_true")
    args = ap.parse_args()

    paths = sorted(args.src_dir.glob("*.png"))
    if not paths:
        raise SystemExit(f"no PNGs in {args.src_dir}")
    treatments = list(GRAIN) if args.grain == "all" else [args.grain]

    print(f"{'icon':8s} {'ring cov':>9s}  {'bg roughness by treatment':>40s}")
    for p in paths:
        img = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)
        rgb, alpha = img[..., :3], img[..., 3] / 255.0
        n = img.shape[0]
        c = (n - 1) / 2
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        dx, dy = xx - c, yy - c
        r = np.hypot(dx, dy)
        disc = alpha > 0.99

        ink = ink_coverage(rgb, dx, r, disc)
        rough, ring = [], None
        for g in treatments:
            gi = GRAIN[g](ink, dx, r, disc)
            h, ring = tone_curve(gi, r, disc)
            h = gaussian_filter(h, INK_BLUR)

            for name, hp in profiles(h, r, args.radius, alpha).items():
                d = args.out_dir / g / name
                d.mkdir(parents=True, exist_ok=True)
                save16(hp, d / f"{p.stem}_height.png")
                if not args.no_normals:
                    nm = normal_map(hp)
                    Image.fromarray((nm * 255).astype(np.uint8), "RGB").save(
                        d / f"{p.stem}_normal.png")

            # per side, so the light half's grain shows up in the numbers
            plain = disc & (((r > 105) & (r < 120)) | ((r > 137) & (r < 150)))
            sds = []
            for side in (dx < 0, dx >= 0):
                v = gi[plain & side]
                v = v[np.abs(v) < 0.08]
                sds.append(1.4826 * np.median(np.abs(v - np.median(v))) if v.size else 0.0)
            rough.append(f"{g}={100*sds[0]:.1f}/{100*sds[1]:.1f}%")
        print(f"{p.stem:8s} {ring:9.3f}  " + "  ".join(rough))

    print(f"\n{len(paths)} icons x {len(treatments)} grain x 3 profiles -> {args.out_dir}")
    print("roughness is left/right robust sd of ink coverage on the flat field")


if __name__ == "__main__":
    main()
