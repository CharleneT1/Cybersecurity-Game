# Assets

`world_map.png` is a precision-generated equirectangular (Plate Carrée) world
map: exactly 2:1, spanning the full -180..180 / -90..90 range edge to edge, so
it matches the lon/lat -> pixel math in `main.py`'s `Projection` class exactly.
It's rendered from [Natural Earth](https://www.naturalearthdata.com/) coastline
data (public domain) via Cartopy, not a downloaded photo/graphic, which is what
guarantees the exact projection and aspect ratio.

Regenerate it with:

```bash
pip install cartopy matplotlib
python3 - <<'EOF'
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

OCEAN = "#0d1522"
LAND = "#243a34"
COAST = "#4d7a6c"

fig = plt.figure(figsize=(24, 12), dpi=100)
ax = plt.axes(projection=ccrs.PlateCarree())
ax.set_global()
ax.set_extent([-180, 180, -90, 90], crs=ccrs.PlateCarree())
ax.set_facecolor(OCEAN)
ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor=LAND, edgecolor=COAST, linewidth=0.7, zorder=1)
ax.add_feature(cfeature.LAKES.with_scale("50m"), facecolor=OCEAN, edgecolor=COAST, linewidth=0.4, zorder=2)
(ax.outline_patch if hasattr(ax, "outline_patch") else ax.spines["geo"]).set_visible(False)
ax.set_position([0, 0, 1, 1])
plt.axis("off")
fig.savefig("assets/world_map.png", facecolor=OCEAN, edgecolor="none", pad_inches=0)
EOF
```

Node placement itself (`is_on_land` in `main.py`) does not sample this image's
pixels -- it tests against the traced coastline polygons in `map_polygons.py`.
That keeps placement exact regardless of the image's color scheme, and means
this file can be restyled freely without risking node/coastline misalignment.
