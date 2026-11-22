# Feature Spec: Rainfall Data Across Areas, Months and Years

## User story
"I'm buying in Pune. Some areas flood every monsoon — I want to know how much rain each locality actually gets, and which months are worst."

## What it does
1. **Rainfall overlay** on the map: colour-coded by annual rainfall (green = moderate, blue = heavy, purple = very heavy)
2. **Monthly rainfall chart** on each society card showing Jan–Dec pattern
3. **Locality-level comparison**: which areas get more rain vs less
4. **Year-over-year trend**: is rainfall increasing (climate change signal)?
5. **Flood risk correlation**: combine with existing rivers/flood overlay to highlight waterlogging-prone areas

## Data sources

### Source 1: IMD Gridded Rainfall (best — 0.25° resolution)
- India Meteorological Department publishes daily gridded rainfall at 0.25° × 0.25° (~25km) resolution
- Download: https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html
- Format: NetCDF (.nc) files, one per year
- Coverage: 1901–present, all of India
- **Limitation**: 25km grid is coarse — Pune city fits in ~4 grid cells. Good for city-level and broad area comparisons.

### Source 2: IMD Station Data (granular but sparse)
- IMD weather stations report daily rainfall
- Pune has stations at Shivajinagar, Pashan, Lohegaon (airport), Chinchwad
- Published in: IMD annual reports, data.gov.in
- Format: CSV or PDF tables
- **Better granularity**: station-level, but only 3-5 stations per city

### Source 3: NASA GPM IMERG (best resolution — 0.1°)
- Global Precipitation Measurement mission
- 0.1° × 0.1° (~10km) resolution, half-hourly to monthly
- Free via NASA GES DISC: https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGM_07/summary
- Format: HDF5/NetCDF, monthly aggregates available
- API: OpenDAP or direct download
- **Recommended for MVP**: monthly aggregates, last 5 years

### Source 4: Open-Meteo Historical Weather API (easiest)
- Free, no API key needed
- Historical daily weather for any lat/lng
- https://archive-api.open-meteo.com/v1/archive?latitude=18.52&longitude=73.85&start_date=2019-01-01&end_date=2024-12-31&daily=precipitation_sum
- Returns JSON with daily precipitation in mm
- **Best for MVP**: query per locality centroid, aggregate monthly

### Recommended approach: Open-Meteo for MVP, NASA GPM for production

## Pipeline: `pipeline/rain_fetch.py` (new file)

```python
"""Fetch historical rainfall for each locality in a city.

Uses Open-Meteo archive API (free, no key). Falls back to city-level
IMD normals if the API is unavailable.

usage: python rain_fetch.py <city>
Output: pipeline/out/<city>/rainfall.json
"""
import json
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

CITIES = json.loads((Path(__file__).parent.parent / "data" / "cities.json").read_text())
OUT = Path(__file__).parent / "out"

OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"

# IMD long-term monthly normals (mm) as fallback
# Source: IMD Climatological Tables
IMD_NORMALS = {
    "pune": [2, 1, 3, 12, 25, 128, 187, 128, 120, 73, 28, 7],       # Jan-Dec
    "gurgaon": [15, 18, 13, 7, 20, 52, 202, 190, 112, 15, 5, 7],
    "bangalore": [3, 7, 14, 47, 119, 81, 110, 137, 195, 155, 58, 14],
    "mumbai": [1, 1, 0, 1, 14, 574, 840, 553, 341, 76, 15, 4],
    "hyderabad": [8, 11, 15, 24, 44, 107, 165, 176, 163, 93, 24, 6],
}

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fetch_locality_rain(lat, lng, start_year=2019, end_year=2024):
    """Fetch daily precipitation from Open-Meteo, return monthly averages."""
    url = (f"{OPEN_METEO}?latitude={lat:.4f}&longitude={lng:.4f}"
           f"&start_date={start_year}-01-01&end_date={end_year}-12-31"
           f"&daily=precipitation_sum&timezone=Asia/Kolkata")
    req = urllib.request.Request(url, headers={"User-Agent": "Property-Finder/0.1"})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    
    dates = resp["daily"]["time"]          # ["2019-01-01", ...]
    precip = resp["daily"]["precipitation_sum"]  # [0.0, 1.2, ...]
    
    # Aggregate: monthly totals per year, then average across years
    by_month_year = defaultdict(list)  # (month_idx) -> [total_per_year]
    year_totals = defaultdict(float)
    
    for date_str, mm in zip(dates, precip):
        if mm is None:
            continue
        year = int(date_str[:4])
        month = int(date_str[5:7]) - 1  # 0-indexed
        year_totals[(year, month)] = year_totals.get((year, month), 0) + mm
    
    monthly_avg = []
    for m in range(12):
        vals = [year_totals.get((y, m), 0) for y in range(start_year, end_year + 1)]
        monthly_avg.append(round(sum(vals) / len(vals), 1))
    
    annual_avg = round(sum(monthly_avg), 1)
    
    # Year-over-year annual totals for trend
    yearly = []
    for y in range(start_year, end_year + 1):
        total = sum(year_totals.get((y, m), 0) for m in range(12))
        yearly.append({"year": y, "mm": round(total, 1)})
    
    return {
        "monthly_avg": monthly_avg,  # 12 values, Jan-Dec, in mm
        "annual_avg": annual_avg,
        "yearly": yearly,            # [{year, mm}, ...]
        "wettest_month": MONTH_NAMES[monthly_avg.index(max(monthly_avg))],
        "monsoon_pct": round(sum(monthly_avg[5:9]) / annual_avg * 100) if annual_avg else 0,
    }


def fetch(city):
    """Fetch rainfall for each locality centroid in the city."""
    if city not in CITIES:
        raise SystemExit(f"unknown city {city}")
    
    # Load built city data to get locality centroids
    city_json = Path(__file__).parent.parent / "web" / "public" / "data" / f"{city}.json"
    if not city_json.exists():
        raise SystemExit(f"build {city} first: {city_json} not found")
    
    data = json.loads(city_json.read_text(encoding="utf-8"))
    
    # Compute locality centroids
    loc_coords = defaultdict(lambda: {"lats": [], "lngs": []})
    for s in data["societies"]:
        loc = (s.get("locality") or "").strip()
        if loc and s.get("lat") and s.get("lng"):
            loc_coords[loc]["lats"].append(s["lat"])
            loc_coords[loc]["lngs"].append(s["lng"])
    
    localities = {}
    for loc, coords in loc_coords.items():
        lat = sum(coords["lats"]) / len(coords["lats"])
        lng = sum(coords["lngs"]) / len(coords["lngs"])
        localities[loc] = {"lat": round(lat, 4), "lng": round(lng, 4)}
    
    print(f"{len(localities)} localities to fetch rainfall for")
    
    # Group nearby localities to reduce API calls
    # Round to 0.02° grid (~2km) — localities in the same cell share data
    grid = {}
    loc_to_grid = {}
    for loc, pos in localities.items():
        key = (round(pos["lat"] / 0.02) * 0.02, round(pos["lng"] / 0.02) * 0.02)
        grid.setdefault(key, []).append(loc)
        loc_to_grid[loc] = key
    
    print(f"grouped into {len(grid)} grid cells (2km resolution)")
    
    # Fetch one per grid cell
    grid_data = {}
    for i, (key, locs) in enumerate(grid.items()):
        lat, lng = key
        try:
            rain = fetch_locality_rain(lat, lng)
            grid_data[key] = rain
            print(f"  {i+1}/{len(grid)}: {lat:.3f},{lng:.3f} -> {rain['annual_avg']} mm/year ({', '.join(locs[:3])})")
        except Exception as e:
            print(f"  {i+1}/{len(grid)}: FAILED {e}, using IMD normals")
            normals = IMD_NORMALS.get(city, [0]*12)
            grid_data[key] = {
                "monthly_avg": normals,
                "annual_avg": round(sum(normals), 1),
                "yearly": [],
                "wettest_month": MONTH_NAMES[normals.index(max(normals))] if any(normals) else "Jul",
                "monsoon_pct": round(sum(normals[5:9]) / sum(normals) * 100) if sum(normals) else 0,
            }
        time.sleep(0.5)  # polite rate limiting
    
    # Map back to localities
    result = {
        "city": city,
        "source": "Open-Meteo Historical Weather API (ERA5 reanalysis)",
        "period": "2019-2024",
        "month_names": MONTH_NAMES,
        "localities": {},
    }
    for loc, pos in localities.items():
        key = loc_to_grid[loc]
        rain = grid_data.get(key)
        if rain:
            result["localities"][loc] = {
                **rain,
                "lat": pos["lat"],
                "lng": pos["lng"],
            }
    
    # City-wide stats
    all_annual = [v["annual_avg"] for v in result["localities"].values() if v["annual_avg"]]
    if all_annual:
        result["city_avg"] = round(sum(all_annual) / len(all_annual), 1)
        result["city_min"] = round(min(all_annual), 1)
        result["city_max"] = round(max(all_annual), 1)
    
    dest = OUT / city / "rainfall.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    print(f"rainfall -> {dest} ({len(result['localities'])} localities)")
    return dest


if __name__ == "__main__":
    fetch(sys.argv[1] if len(sys.argv) > 1 else "pune")
```

## Integration in `build_city.py`

```python
# After noise.geojson, copy rainfall.json to web data
for key, fname in (..., ("rainfall", "rainfall.json")):
    src = out / fname
    if src.exists():
        shutil.copy(src, WEB / f"{city}-{fname}")
        overlays.append(key)
```

Add to each society from the rainfall data:
```python
def add_rainfall(societies, rainfall_data):
    """Assign locality rainfall to each society."""
    locs = rainfall_data.get("localities", {})
    for s in societies:
        loc = (s.get("locality") or "").strip()
        rain = locs.get(loc)
        if rain:
            s["rain_annual"] = rain["annual_avg"]
            s["rain_monthly"] = rain["monthly_avg"]
            s["rain_monsoon_pct"] = rain["monsoon_pct"]
```

## Frontend changes

### Overlay: rainfall choropleth
Add checkbox in layers panel:
```html
<label class="sw"><input type="checkbox" id="dl-rain"> Rainfall</label>
```

When enabled, draw circles at locality centroids with size/colour based on annual rainfall:
```javascript
async function toggleRain() {
  const on = $('dl-rain').checked;
  if (on && !map.getSource('rain-data')) {
    const rain = await loadJson(`/data/${cityId}-rainfall.json`);
    rainData = rain;
    const features = Object.entries(rain.localities).map(([name, loc]) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [loc.lng, loc.lat] },
      properties: { name, annual: loc.annual_avg, monsoon_pct: loc.monsoon_pct }
    }));
    map.addSource('rain-data', { type: 'geojson', data: { type: 'FeatureCollection', features } });
    map.addLayer({
      id: 'rain-circles', type: 'circle', source: 'rain-data',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 12, 14, 24],
        'circle-color': ['interpolate', ['linear'], ['get', 'annual'],
          400, '#93c5fd',   // light blue = moderate
          700, '#3b82f6',   // blue = heavy
          1000, '#6366f1',  // indigo = very heavy
          1500, '#7c3aed',  // purple = extreme
        ],
        'circle-opacity': 0.5,
        'circle-stroke-width': 1,
        'circle-stroke-color': '#fff',
        'circle-stroke-opacity': 0.3,
      }
    }, 'labels');
    // Labels
    map.addLayer({
      id: 'rain-labels', type: 'symbol', source: 'rain-data',
      layout: {
        'text-field': ['concat', ['to-string', ['round', ['get', 'annual']]], ' mm'],
        'text-size': 10,
        'text-font': ['Inter Regular'],
      },
      paint: { 'text-color': '#e0e7ff', 'text-halo-color': '#0b0b0c', 'text-halo-width': 1.5 }
    });
  }
  showOverlay(['rain-circles', 'rain-labels'], on);
}
```

### Monthly rainfall chart on society card
Show a small bar chart of Jan–Dec rainfall:

```javascript
function rainfallChart(monthly, monsoonPct, annual) {
  if (!monthly || monthly.length !== 12) return '';
  const max = Math.max(...monthly) || 1;
  const months = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
  
  const bars = monthly.map((mm, i) => {
    const h = Math.max(2, Math.round((mm / max) * 48));
    const isMonsoon = i >= 5 && i <= 8;
    const color = isMonsoon ? '#3b82f6' : '#93c5fd';
    return `<div class="rain-bar" title="${MONTH_NAMES[i]}: ${mm} mm">
      <i style="height:${h}px;background:${color}"></i>
      <span>${months[i]}</span>
    </div>`;
  }).join('');
  
  return `
    <div class="rain-section">
      <div class="k">Rainfall · ${annual} mm/year · ${monsoonPct}% in monsoon</div>
      <div class="rain-chart">${bars}</div>
    </div>
  `;
}
```

### Where to show on card
In the card rendering, after the nearby section:
```javascript
const rain = s.rain_annual ? rainfallChart(s.rain_monthly, s.rain_monsoon_pct, s.rain_annual) : '';
```

### Sort option
```html
<option value="rain-low">Least rainfall</option>
```
Sort: `(a.rain_annual ?? 999) - (b.rain_annual ?? 999)` — useful for people who hate rain.

## Styles
```css
.rain-section { margin: 8px 0; }
.rain-chart { display: flex; align-items: flex-end; gap: 3px; height: 64px; }
.rain-bar { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; height: 100%; gap: 2px; }
.rain-bar i { display: block; width: 100%; border-radius: 2px 2px 0 0; min-height: 2px; }
.rain-bar span { font-size: 8px; color: var(--muted); }
```

## Performance
- Open-Meteo API: free, no key, ~100 requests before rate limit
- With 2km grid grouping, Pune (~80 localities) → ~25-30 API calls
- Each call returns 6 years of daily data (~2KB response)
- Total fetch time: ~15-20 seconds per city
- Cache the rainfall.json — it doesn't change often (re-fetch yearly)

## Files to create/change
- `pipeline/rain_fetch.py` — NEW: fetch rainfall from Open-Meteo API
- `pipeline/build_city.py` — copy rainfall.json to web data, add `rain_*` to societies
- `web/index.html` — add "Rainfall" overlay checkbox, rain sort option
- `web/src/main.js` — add `toggleRain()`, `rainfallChart()`, rain overlay rendering
- `web/src/style.css` — rain chart bar styles

## Don't touch
- Existing overlays (metro, schools, rivers, AQI, noise)
- Filter logic
- Colour-by modes (rainfall as colour-by is a stretch goal)
