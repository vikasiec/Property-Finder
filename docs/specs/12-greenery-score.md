# Feature Spec: Greenery Score

## User story
"I want to live somewhere green — not just 'near a park' but actually surrounded by trees and open space, not concrete. Show me which localities are genuinely green vs built-up."

## What it does
1. **Greenery score (0–100)** per society from satellite vegetation data in a 500m radius
2. **Colour-by mode** on the map: green = lush, grey = concrete-heavy
3. **Greenery overlay**: heatmap showing vegetation density across the city
4. **Card section** showing the score with a label (Lush / Moderate / Sparse / Concrete)
5. **Sort option**: sort societies by greenery score
6. **Trend** (stretch): compare NDVI across years to show if area is losing green cover

## Data source: Sentinel-2 NDVI via Google Earth Engine or free alternatives

### What is NDVI?
Normalized Difference Vegetation Index — measures live green vegetation from satellite imagery. Ranges from -1 to +1, where:
- **0.6–0.9** = dense forest/garden
- **0.3–0.6** = moderate vegetation (parks, tree-lined streets)
- **0.1–0.3** = sparse vegetation (some trees, mostly built)
- **< 0.1** = bare soil, concrete, water

### Source 1: Sentinel Hub Statistical API (recommended for MVP)
- Free tier: 30,000 requests/month
- 10m resolution Sentinel-2 imagery
- Returns mean NDVI for any polygon/circle without downloading full images
- API: `https://services.sentinel-hub.com/api/v1/statistics`
- Needs free account + OAuth client ID/secret
- **Best approach**: query mean NDVI in a 500m circle around each society

### Source 2: Google Earth Engine (best, needs setup)
- Free for non-commercial use
- Python API: `ee.ImageCollection('COPERNICUS/S2_SR')`
- Can compute NDVI for any geometry, any date range
- Requires GEE account approval (takes 1-2 days)
- Can export gridded NDVI as GeoTIFF for the whole city bbox

### Source 3: OpenStreetMap land use (simplest fallback)
- Overpass API query for `landuse=forest|grass|meadow|orchard|farmland`, `leisure=park|garden`, `natural=wood|scrub|grassland`
- Count green area within 500m of each society
- **Less accurate** than satellite — misses private gardens, tree cover on streets, untagged green spaces
- **No account needed**, free

### Source 4: Copernicus Global Land Service
- Pre-computed NDVI at 300m resolution, 10-day composites
- Download: `https://land.copernicus.eu/global/products/ndvi`
- Format: NetCDF/GeoTIFF
- Free, no account needed for download
- **Coarser** than Sentinel-2 but zero API calls

### Recommended: OSM green area for MVP, Sentinel Hub for production

## Pipeline: `pipeline/green_fetch.py` (new file)

```python
"""Greenery score per society from OSM land-use data + optional NDVI.

MVP uses Overpass API to compute green-area fraction within 500m of each
society. Production path uses Sentinel Hub Statistical API for real NDVI.

usage: python green_fetch.py <city>
Output: pipeline/out/<city>/greenery.json
"""
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CITIES = json.loads((Path(__file__).parent.parent / "data" / "cities.json").read_text())
OUT = Path(__file__).parent / "out"

# Overpass query for green polygons in the city bbox
GREEN_QUERY = """
[out:json][timeout:90][bbox:{s},{w},{n},{e}];
(
  way["landuse"~"^(forest|grass|meadow|orchard|farmland|vineyard|allotments)$"];
  way["leisure"~"^(park|garden|nature_reserve|golf_course)$"];
  way["natural"~"^(wood|scrub|grassland|heath)$"];
  relation["landuse"~"^(forest|grass|meadow|orchard|farmland)$"];
  relation["leisure"~"^(park|garden|nature_reserve)$"];
  relation["natural"~"^(wood|scrub|grassland)$"];
);
out geom;
"""

M_PER_DEG_LAT = 111_320


def m_per_deg_lng(lat):
    return M_PER_DEG_LAT * math.cos(math.radians(lat))


def polygon_area_m2(coords):
    """Shoelace formula for polygon area in approximate square metres."""
    if len(coords) < 3:
        return 0
    lat0 = coords[0][1]
    mx = m_per_deg_lng(lat0)
    my = M_PER_DEG_LAT
    area = 0
    n = len(coords)
    for i in range(n):
        j = (i + 1) % n
        x1, y1 = coords[i][0] * mx, coords[i][1] * my
        x2, y2 = coords[j][0] * mx, coords[j][1] * my
        area += x1 * y2 - x2 * y1
    return abs(area) / 2


def point_in_circle(px, py, cx, cy, radius_m):
    """Check if point (lng, lat) is within radius_m of centre (clng, clat)."""
    dx = (px - cx) * m_per_deg_lng((py + cy) / 2)
    dy = (py - cy) * M_PER_DEG_LAT
    return (dx * dx + dy * dy) <= radius_m * radius_m


def fetch_green_polygons(bbox):
    """Fetch green land-use polygons from Overpass API."""
    south, west, north, east = bbox
    query = GREEN_QUERY.format(s=south, w=west, n=north, e=east)
    body = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=body,
        headers={"User-Agent": "Property-Finder/0.1 (greenery)", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    polygons = []
    for el in payload.get("elements", []):
        geom = el.get("geometry")
        if not geom:
            continue
        coords = [(p["lon"], p["lat"]) for p in geom]
        if len(coords) < 3:
            continue
        tags = el.get("tags") or {}
        kind = tags.get("landuse") or tags.get("leisure") or tags.get("natural") or "green"
        area = polygon_area_m2(coords)
        if area < 100:
            continue
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        polygons.append({
            "coords": coords,
            "centroid": (cx, cy),
            "area_m2": area,
            "kind": kind,
        })
    return polygons


def green_area_in_radius(lat, lng, polygons, radius_m=500):
    """Sum area of green polygons whose centroid is within radius_m of (lat, lng)."""
    total = 0
    for p in polygons:
        cx, cy = p["centroid"]
        if point_in_circle(cx, cy, lng, lat, radius_m):
            total += p["area_m2"]
    return total


def score_from_area(green_m2, radius_m=500):
    """Convert green area fraction to 0-100 score.

    A 500m radius circle has area ~785,000 m². Scoring:
    - 100: > 40% green (314,000+ m²) — park/forest area
    -  75: 20-40% green — well-planted suburb
    -  50: 10-20% green — moderate
    -  25: 5-10% green — sparse
    -   0: < 2% green — dense concrete
    Linear interpolation between breakpoints.
    """
    circle_area = math.pi * radius_m * radius_m
    fraction = green_m2 / circle_area if circle_area else 0
    fraction = min(fraction, 0.5)  # cap at 50%

    breakpoints = [(0.02, 0), (0.05, 25), (0.10, 50), (0.20, 75), (0.40, 100)]
    if fraction <= breakpoints[0][0]:
        return 0
    for i in range(1, len(breakpoints)):
        f1, s1 = breakpoints[i - 1]
        f2, s2 = breakpoints[i]
        if fraction <= f2:
            t = (fraction - f1) / (f2 - f1)
            return round(s1 + t * (s2 - s1))
    return 100


def label_from_score(score):
    if score >= 75: return "Lush"
    if score >= 50: return "Moderate"
    if score >= 25: return "Sparse"
    return "Concrete"


def fetch(city):
    if city not in CITIES:
        raise SystemExit(f"unknown city {city}")
    bbox = CITIES[city]["bbox"]

    # Load built city data
    city_json = Path(__file__).parent.parent / "web" / "public" / "data" / f"{city}.json"
    if not city_json.exists():
        raise SystemExit(f"build {city} first: {city_json} not found")
    data = json.loads(city_json.read_text(encoding="utf-8"))

    print(f"fetching green polygons for {city}...")
    polygons = fetch_green_polygons(bbox)
    print(f"  {len(polygons)} green polygons, total area {sum(p['area_m2'] for p in polygons)/1e6:.1f} km²")

    # Build spatial grid index for polygons (0.005° cells ~ 500m)
    grid = {}
    for p in polygons:
        cx, cy = p["centroid"]
        key = (round(cy / 0.005), round(cx / 0.005))
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                k = (key[0] + dy, key[1] + dx)
                grid.setdefault(k, []).append(p)

    def nearby_polygons(lat, lng):
        key = (round(lat / 0.005), round(lng / 0.005))
        return grid.get(key, [])

    # Score each society
    results = {}
    for s in data["societies"]:
        lat, lng = s.get("lat"), s.get("lng")
        if not lat or not lng:
            continue
        nearby = nearby_polygons(lat, lng)
        green_m2 = green_area_in_radius(lat, lng, nearby, radius_m=500)
        score = score_from_area(green_m2)
        sid = s.get("id") or s.get("name")
        results[sid] = {
            "score": score,
            "label": label_from_score(score),
            "green_m2": round(green_m2),
            "nearby_green": len([p for p in nearby if point_in_circle(
                p["centroid"][0], p["centroid"][1], lng, lat, 500)]),
        }

    # Locality averages
    loc_scores = {}
    for s in data["societies"]:
        sid = s.get("id") or s.get("name")
        loc = (s.get("locality") or "").strip()
        if loc and sid in results:
            loc_scores.setdefault(loc, []).append(results[sid]["score"])

    locality_avg = {}
    for loc, scores in loc_scores.items():
        avg = round(sum(scores) / len(scores))
        locality_avg[loc] = {"score": avg, "label": label_from_score(avg), "count": len(scores)}

    output = {
        "city": city,
        "source": "OpenStreetMap land-use polygons via Overpass API",
        "radius_m": 500,
        "total_green_polygons": len(polygons),
        "societies": results,
        "localities": locality_avg,
    }

    # Also export green polygons as GeoJSON for overlay
    overlay_features = []
    for p in polygons:
        if p["area_m2"] < 500:
            continue
        ring = p["coords"]
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        overlay_features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"kind": p["kind"], "area_m2": round(p["area_m2"])},
        })

    out_dir = OUT / city
    out_dir.mkdir(parents=True, exist_ok=True)

    dest = out_dir / "greenery.json"
    dest.write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")
    print(f"greenery scores -> {dest} ({len(results)} societies)")

    overlay_dest = out_dir / "green.geojson"
    overlay_dest.write_text(json.dumps(
        {"type": "FeatureCollection", "features": overlay_features},
        separators=(",", ":")), encoding="utf-8")
    print(f"green overlay -> {overlay_dest} ({len(overlay_features)} polygons)")


if __name__ == "__main__":
    fetch(sys.argv[1] if len(sys.argv) > 1 else "pune")
```

## Integration in `build_city.py`

```python
# Load greenery scores
greenery_path = out / "greenery.json"
if greenery_path.exists():
    greenery = json.loads(greenery_path.read_text(encoding="utf-8"))
    for s in societies:
        sid = s.get("id") or s.get("name")
        g = greenery.get("societies", {}).get(sid)
        if g:
            s["green_score"] = g["score"]
            s["green_label"] = g["label"]

# Copy green.geojson overlay
for key, fname in (..., ("green", "green.geojson")):
    src = out / fname
    if src.exists():
        shutil.copy(src, WEB / f"{city}-{fname}")
        overlays.append(key)
```

## Frontend changes

### Colour-by mode: greenery
Add radio in layers panel:
```html
<label><input type="radio" name="colorby" value="greenery"> Greenery</label>
```

In `setColorBy()`:
```javascript
} else if (mode === 'greenery') {
  const has = data.societies.some(s => s.green_score != null);
  if (!has) {
    // fall back to off, toast "no greenery data"
    return;
  }
  map.setFilter('colorby', ['has', 'green_score']);
  map.setPaintProperty('colorby', 'circle-color', ['interpolate', ['linear'],
    ['coalesce', ['get', 'green_score'], 0],
    0, '#94a3b8',    // grey = concrete
    25, '#fbbf24',   // amber = sparse
    50, '#84cc16',   // lime = moderate
    75, '#22c55e',   // green = good
    100, '#15803d',  // dark green = lush
  ]);
  map.setPaintProperty('colorby', 'circle-opacity', 0.85);
  $('ll-title').textContent = 'Greenery';
  $('ll-dots').innerHTML = '';
  $('ll-lo').textContent = 'Concrete';
  $('ll-hi').textContent = 'Lush';
  document.querySelector('.ll-bar').style.background =
    'linear-gradient(90deg, #94a3b8, #fbbf24, #84cc16, #22c55e, #15803d)';
  document.querySelector('.ll-bar').style.display = '';
  document.querySelector('.ll-labels').style.display = '';
}
```

### Green overlay: parks and forests on map
```html
<label class="sw"><input type="checkbox" id="dl-green"> Green spaces</label>
```

```javascript
async function toggleGreen() {
  const on = $('dl-green').checked;
  if (on && !map.getSource('green-data')) {
    const gj = await loadJson(`/data/${cityId}-green.geojson`);
    map.addSource('green-data', { type: 'geojson', data: gj });
    map.addLayer({
      id: 'green-fill', type: 'fill', source: 'green-data',
      paint: { 'fill-color': '#22c55e', 'fill-opacity': 0.2 }
    }, 'labels');
    map.addLayer({
      id: 'green-line', type: 'line', source: 'green-data',
      paint: { 'line-color': '#22c55e', 'line-width': 1, 'line-opacity': 0.5 }
    }, 'labels');
  }
  showOverlay(['green-fill', 'green-line'], on);
}
```

### Card section
```javascript
function greenBadge(score, label) {
  if (score == null) return '';
  const cls = score >= 75 ? 'green-lush' : score >= 50 ? 'green-mod' : score >= 25 ? 'green-sparse' : 'green-concrete';
  return `<span class="signal ${cls}" title="Greenery: ${score}/100">${label} · ${score}</span>`;
}
```

Add to `signalRows(s)`:
```javascript
if (s.green_score != null) rows.push(greenBadge(s.green_score, s.green_label));
```

### Sort option
```html
<option value="greenery">Greenest first</option>
```
Sort: `(b.green_score ?? 0) - (a.green_score ?? 0)`

### URL param
Add `green` to `syncUrlFromFilters` / `readFiltersFromUrl` for the colour-by and overlay state.

## Styles
```css
.green-lush { background: #15803d; color: #fff; }
.green-mod { background: #84cc16; color: #1a1a1a; }
.green-sparse { background: #fbbf24; color: #1a1a1a; }
.green-concrete { background: #94a3b8; color: #1a1a1a; }
```

## Performance
- Overpass query returns all green polygons in bbox — one API call per city
- Spatial grid index avoids O(n*m) on 29k societies × green polygons
- Scoring is pure math, no external calls per society
- Output: greenery.json (~50KB) + green.geojson (~200KB depending on city)
- Total pipeline time: ~30 seconds per city (mostly Overpass query)

## Files to create/change
- `pipeline/green_fetch.py` — NEW: fetch green polygons from OSM, compute scores
- `pipeline/build_city.py` — load greenery.json, add `green_score`/`green_label` to societies, copy overlay
- `web/index.html` — add "Green spaces" overlay checkbox, greenery colour-by radio, greenery sort option
- `web/src/main.js` — add `toggleGreen()`, greenery colour-by case, `greenBadge()`, greenery sort
- `web/src/style.css` — green badge colour classes

## Don't touch
- Existing overlays (metro, schools, rivers, AQI, noise, rainfall)
- Other colour-by modes
- Filter logic
- Compare mode
