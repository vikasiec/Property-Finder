# Feature Spec: Noise & Pollution Layer

## User story
"I don't want to buy a flat under a flight path or next to a highway and discover it after moving in."

## What it does
Adds a new overlay checkbox **"Noise zones"** in the layers panel (next to Metro routes, Schools, Rivers, Air quality). When enabled, it shows:

1. **Airport flight path cones** — 2km-wide noise corridors extending from runway ends (approach/departure paths). Colour: red-orange gradient fading with distance.
2. **Highway noise buffers** — 200m buffer zones around national highways (NH), state highways (SH), and trunk roads. Colour: amber, semi-transparent.
3. **Railway noise buffers** — 100m buffer zones around rail lines. Colour: amber, lighter than highways.

Each society gets a **noise_score** (0 = quiet, 100 = very noisy) based on proximity to these sources.

## Data source

### Pipeline: `pipeline/noise_fetch.py` (new file)

```python
# Fetches noise-relevant geometry from OpenStreetMap via Overpass API

def fetch_noise_data(city_id):
    """
    Queries:
    1. Airports: aeroway=runway, aeroway=aerodrome within city bbox
    2. Major roads: highway=motorway|trunk|primary within city bbox
    3. Railways: railway=rail|light_rail within city bbox
    
    For each runway, generate two approach cones:
    - 3km long, 2km wide at the far end, tapering to runway width
    - Direction from runway orientation (bearing)
    
    For roads/railways, the raw linestrings are stored;
    buffering happens client-side or in build_city.py
    
    Output: out/<city>/noise.geojson with features:
    - type: "flight_path" | "highway" | "railway"
    - name: road/railway name or airport name
    - noise_level: "high" | "medium" | "low"
    """
```

**Overpass queries:**
```
# Airports and runways
[out:json][bbox:{bbox}];
(
  way["aeroway"="runway"];
  node["aeroway"="aerodrome"];
  way["aeroway"="aerodrome"];
);
out geom;

# Major roads
[out:json][bbox:{bbox}];
way["highway"~"motorway|trunk|primary"](if:t["lanes"]>2 || t["highway"]=="motorway");
out geom;

# Railways  
[out:json][bbox:{bbox}];
way["railway"~"rail|light_rail"];
out geom;
```

### Integration in `build_city.py`

Add `noise_score` to each society:
```python
def calc_noise_score(society, noise_features):
    score = 0
    lat, lng = society['lat'], society['lng']
    
    for f in noise_features:
        dist = min_distance_to_feature(lat, lng, f)
        if f['properties']['type'] == 'flight_path':
            if dist < 500: score = max(score, 95)
            elif dist < 1000: score = max(score, 80)
            elif dist < 2000: score = max(score, 60)
        elif f['properties']['type'] == 'highway':
            if dist < 50: score = max(score, 85)
            elif dist < 100: score = max(score, 65)
            elif dist < 200: score = max(score, 40)
        elif f['properties']['type'] == 'railway':
            if dist < 50: score = max(score, 70)
            elif dist < 100: score = max(score, 50)
    
    return score
```

### Pune-specific airports
- **Pune Airport (Lohegaon)** — lat: 18.5822, lng: 73.9197. Runway bearing ~280/100 degrees.
- Runway is ~2.5km long. Flight cones should extend 3km from each end.

## Frontend changes

### `web/index.html`
Add after the AQI checkbox in the layers panel:
```html
<label class="sw"><input type="checkbox" id="dl-noise"> Noise zones</label>
```

### `web/src/main.js`

```javascript
// New function: toggleNoise()
// Similar pattern to toggleMetro(), toggleSchools(), etc.
// Lazy-loads noise.geojson on first toggle

async function toggleNoise() {
  const on = $('dl-noise').checked;
  if (on && !map.getSource('noise')) {
    const geo = await fetch(`/data/${cityId}-noise.geojson`).then(r => r.json());
    map.addSource('noise', { type: 'geojson', data: geo });
    
    // Flight path cones — red-orange fill
    map.addLayer({
      id: 'noise-flight', type: 'fill', source: 'noise',
      filter: ['==', ['get', 'type'], 'flight_path'],
      paint: {
        'fill-color': '#ff4444',
        'fill-opacity': 0.25
      }
    }, 'societies');
    
    // Highway buffers — amber line with width
    map.addLayer({
      id: 'noise-highway', type: 'line', source: 'noise',
      filter: ['==', ['get', 'type'], 'highway'],
      paint: {
        'line-color': '#ff9800',
        'line-width': 12,  // represents ~200m at typical zoom
        'line-opacity': 0.4
      }
    }, 'societies');
    
    // Railway buffers — lighter amber
    map.addLayer({
      id: 'noise-railway', type: 'line', source: 'noise',
      filter: ['==', ['get', 'type'], 'railway'],
      paint: {
        'line-color': '#ffc107',
        'line-width': 8,
        'line-opacity': 0.3
      }
    }, 'societies');
  }
  ['noise-flight', 'noise-highway', 'noise-railway'].forEach(id => {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
  });
}
```

### Society card
Show noise warning on the card when `noise_score > 50`:
```html
<div class="noise-warn">⚠ Noise zone: Near [highway/flight path/railway]</div>
```

## Colour-by integration
Optionally add "Noise" as a colour-by mode (green = quiet, red = noisy), but this is a stretch goal. The overlay + card warning is the MVP.

## Files to create/change
- `pipeline/noise_fetch.py` — NEW: fetch airports, highways, railways from OSM
- `pipeline/build_city.py` — add `noise_score` to each society, generate `noise.geojson`
- `web/index.html` — add "Noise zones" checkbox
- `web/src/main.js` — add `toggleNoise()`, wire checkbox, show card warning
- `web/src/style.css` — `.noise-warn` styling

## Don't touch
- Existing overlays (metro, schools, flood, AQI)
- Filter logic in `filters.js`
- Pipeline files other than `build_city.py`
