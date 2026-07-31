# BoH Elements of the Soul

Icons of the elements of the soul from Book of Hours, converted to circular images with various heightmaps.

![Circular badges](preview-badges.png)

Heightmaps, one row each for the coin, relief and engraved profiles:

![Heightmaps](preview-depth.png)

`badges/` holds the nine finished badges: 336×336 PNG, RGBA, 324px disc.

## Scripts

Need `numpy`, `pillow` and `scipy`.

- `python3 circularize.py <src_dir> <out_dir>` — squares to circular badges.
- `python3 depthmaps.py badges <out_dir>` — badges to 16-bit heightmaps and normal maps, in three profiles and three grain treatments.
