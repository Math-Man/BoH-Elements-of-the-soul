# BoH Elements of the Soul

Icons of the elements of the soul from Book of Hours, converted to circular images with various heightmaps.

![Circular badges](preview-badges.png)

Heightmaps, one row each for the coin, relief and engraved profiles:

![Heightmaps](preview-depth.png)

`badges/` holds the nine finished badges: 336×336 PNG, RGBA, 324px disc.

`heightmaps/<grain>/<profile>/` holds 16-bit heightmaps and matching normal maps, for the three profiles above and three grain treatments (`asis`, `mirrored`, `suppressed`). The light half of the original artwork carries a grain texture the dark half doesn't, so `mirrored` copies it across and `suppressed` removes it.

## Scripts

Need `numpy`, `pillow` and `scipy`.

- `python3 circularize.py <src_dir> <out_dir>` — squares to circular badges.
- `python3 depthmaps.py badges <out_dir>` — badges to the heightmaps and normal maps above.
