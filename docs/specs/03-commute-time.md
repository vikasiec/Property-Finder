# Feature Spec: Real Commute Time (OSRM)

## User story
"5 km from my office means nothing. What I care about is 'will I get there in 30 minutes?'"

## What it does
Replaces the current radius-based commute mode with **actual drive/transit time isochrones**. User pins their workplace, picks a commute time (15/30/45/60 min), and sees a real travel-time boundary on the map. Societies inside the isochrone light up; others dim.

## Current commute mode (reference)
- File: `web/src/main.js`, `web/index.html` lines 170-179
- User clicks map to pin workplace, adjusts radius slider (1-20 km)
- Straight-line distance filter: `haversine(society, pin) <= radius`
- Shows commute stats: society count, median price within radius
- State: `commuteMode`, `commutePin`, `commuteRadiusKm`

## Architecture

### Option A: Self-hosted OSRM on DGX (recommended)
- OSRM (Open Source Routing Machine) is free, fast, and self-hostable
- Pre-process India OSM extract once, serve routing queries locally
- **DGX setup:**
```bash
# Download India extract
wget https://download.geofabrik.de/asia/india-latest.osm.pbf

# Extract Maharashtra/Karnataka subset (optional, faster)
osmium extract -b 72.5,17.5,74.5,19.5 india-latest.osm.pbf -o pune-region.osm.pbf

# Process for car routing
docker run -t -v $(pwd):/data ghcr.io/project-osrm/osrm-backend osrm-extract -p /opt/car.lua /data/pune-region.osm.pbf
docker run -t -v $(pwd):/data ghcr.io/project-osrm/osrm-backend osrm-partition /data/pune-region.osrm
docker run -t -v $(pwd):/data ghcr.io/project-osrm/osrm-backend osrm-customize /data/pune-region.osrm

# Serve
docker run -t -p 5000:5000 -v $(pwd):/data ghcr.io/project-osrm/osrm-backend osrm-routed --algorithm mld /data/pune-region.osrm
```

### Option B: Pre-compute at build time (no runtime server)
- During `build_city.py`, compute drive time from every society to a grid of "likely workplace" points
- Store as a lookup: given a pin, interpolate from nearest grid points
- Pro: no server needed. Con: less accurate, large data, doesn't support arbitrary pins

### Option C: Use OSRM's public demo server (simplest but rate-limited)
- `https://router.project-osrm.org/table/v1/driving/{coords}` 
- Rate limit: ~1 req/sec, fine for real-time single queries
- Use for MVP, switch to self-hosted for production

**Recommendation: Start with Option C for MVP, deploy Option A on DGX for production.**

## OSRM API usage

### Table API (many-to-one)
Given the pinned workplace and all visible societies, compute drive times in one call:
```
GET /table/v1/driving/{lng0},{lat0};{lng1},{lat1};...;{lngN},{latN}
    ?sources=0           // workplace is source
    &annotations=duration
```

Returns a matrix of durations in seconds. One call handles up to ~100 coordinates. For 29k societies, batch by locality or use the isochrone approach.

### Isochrone approach (better for visualization)
Use OSRM + Turf.js to generate an isochrone polygon:
1. Query OSRM table from workplace to a grid of points (e.g., 200 points in a 20km radius)
2. Classify each point by travel time bucket (15/30/45/60 min)
3. Use Turf.js `concave()` or `convexHull()` to draw the boundary
4. Test each society: point-in-polygon

### Practical approach (hybrid)
1. When user pins workplace, fetch drive times to **visible/filtered societies only** (usually < 1000 after filters)
2. Batch OSRM table queries in groups of 100
3. Cache results per pin location (round to ~100m grid)
4. Draw isochrone from the results

## Frontend changes

### `web/index.html`
Replace the commute radius slider with time-based controls:
```html
<div id="commute-controls" hidden>
  <div class="commute-place" id="commute-place"></div>
  <div class="k row">
    <span>Commute mode</span>
    <span class="seg small" id="commute-mode-seg">
      <button data-cm="radius">Radius</button>
      <button data-cm="drive">Drive</button>
      <button data-cm="transit">Transit</button>
    </span>
  </div>
  <!-- Show radius slider when mode=radius (existing) -->
  <div id="commute-radius-controls">
    <div class="k row"><span>Radius</span><span class="val" id="commute-val">5 km</span></div>
    <input type="range" id="commute-range" min="1" max="20" step="0.5" value="5">
  </div>
  <!-- Show time selector when mode=drive or transit -->
  <div id="commute-time-controls" hidden>
    <div class="k row"><span>Max commute</span><span class="val" id="commute-time-val">30 min</span></div>
    <input type="range" id="commute-time-range" min="10" max="60" step="5" value="30">
    <div class="fine" id="commute-time-note">Drive time via OSRM (morning traffic not modelled)</div>
  </div>
  <div class="commute-stats" id="commute-stats"></div>
  <button class="linkbtn" id="commute-clear">Clear pin</button>
</div>
```

### `web/src/main.js`

```javascript
// OSRM routing
const OSRM_BASE = 'https://router.project-osrm.org'; // switch to self-hosted later

async function fetchDriveTimes(pin, societies) {
  // Batch societies in groups of 99 (OSRM limit: 100 coords including source)
  const BATCH = 99;
  const results = new Map();
  
  for (let i = 0; i < societies.length; i += BATCH) {
    const batch = societies.slice(i, i + BATCH);
    const coords = [
      `${pin.lng},${pin.lat}`,
      ...batch.map(s => `${s.lng},${s.lat}`)
    ].join(';');
    
    const url = `${OSRM_BASE}/table/v1/driving/${coords}?sources=0&annotations=duration`;
    const resp = await fetch(url).then(r => r.json());
    
    if (resp.code === 'Ok') {
      const durations = resp.durations[0]; // first row = from source
      batch.forEach((s, j) => {
        results.set(s.id, Math.round(durations[j + 1] / 60)); // seconds -> minutes
      });
    }
    
    // Rate limit: 1 req/sec for public OSRM
    if (i + BATCH < societies.length) {
      await new Promise(r => setTimeout(r, 1100));
    }
  }
  
  return results; // Map<society_id, minutes>
}

// When pin is set and mode is "drive":
async function updateCommuteTimes() {
  if (!commutePin || commuteTimeMode === 'radius') return;
  
  $('commute-time-note').textContent = 'Calculating drive times...';
  
  // Only compute for societies passing current filters (reduces API calls)
  const filtered = data.societies.filter(s => states.get(s.id) !== 'no');
  const times = await fetchDriveTimes(commutePin, filtered);
  
  // Store on each society for sorting
  filtered.forEach(s => { s._driveMin = times.get(s.id) ?? null; });
  
  // Apply time filter
  const maxMin = parseInt($('commute-time-range').value);
  filtered.forEach(s => {
    if (s._driveMin != null && s._driveMin > maxMin) {
      states.set(s.id, 'no'); // dim it
    }
  });
  
  setStates(map, states);
  updateCount();
  
  const inRange = filtered.filter(s => s._driveMin != null && s._driveMin <= maxMin);
  $('commute-stats').innerHTML = `
    <b>${inRange.length}</b> societies within ${maxMin} min drive
    <br><span class="fine">Median: ${median(inRange.map(s => s._driveMin))} min</span>
  `;
  $('commute-time-note').textContent = 'Drive time via OSRM (morning traffic not modelled)';
}
```

### Sort option
Add "Commute time" sort when commute drive/transit mode is active:
```javascript
// In the sort select, dynamically add:
if (commuteTimeMode !== 'radius') {
  sortOptions.push({ value: 'commute', label: 'Shortest commute' });
}

// Sort function:
case 'commute':
  return (a._driveMin ?? 999) - (b._driveMin ?? 999);
```

### Isochrone visualization on map
Draw the commute boundary as a polygon:
```javascript
// After computing drive times, draw isochrone
function drawIsochrone(pin, societies, maxMin) {
  const inRange = societies.filter(s => s._driveMin != null && s._driveMin <= maxMin);
  if (inRange.length < 3) return;
  
  // Use Turf.js concave hull of in-range society points
  const points = turf.featureCollection(
    inRange.map(s => turf.point([s.lng, s.lat]))
  );
  const hull = turf.concave(points, { maxEdge: 2, units: 'kilometers' });
  
  if (map.getSource('isochrone')) {
    map.getSource('isochrone').setData(hull);
  } else {
    map.addSource('isochrone', { type: 'geojson', data: hull });
    map.addLayer({
      id: 'isochrone-fill', type: 'fill', source: 'isochrone',
      paint: { 'fill-color': '#00bcd4', 'fill-opacity': 0.1 }
    }, 'societies');
    map.addLayer({
      id: 'isochrone-line', type: 'line', source: 'isochrone',
      paint: { 'line-color': '#00bcd4', 'line-width': 2, 'line-dasharray': [3, 2] }
    }, 'societies');
  }
}
```

### Dependencies
- **Turf.js** — add `@turf/turf` or just `@turf/concave` + `@turf/helpers` for hull computation
- Or skip the polygon and just show drive time labels on each society marker

## Card changes
When commute time is computed, show on the society card:
```html
<div class="commute-info">🚗 ${driveMin} min drive from ${placeName}</div>
```

## Performance considerations
- 29k societies × OSRM table = ~290 batches × 1 sec each = ~5 min on public OSRM
- **Solution**: Only compute for filtered societies (usually 1-5k after BHK/budget filters)
- **Solution**: Cache by pin grid cell (100m resolution)
- **Self-hosted OSRM**: No rate limit, <100ms per 100-coord batch = 29k in <30 sec

## Files to create/change
- `web/index.html` — replace commute controls with mode toggle + time slider
- `web/src/main.js` — add `fetchDriveTimes()`, `updateCommuteTimes()`, `drawIsochrone()`, commute mode toggle
- `web/src/style.css` — commute time controls styling
- `web/src/filters.js` — add "commute" sort option
- `package.json` — add `@turf/concave` and `@turf/helpers` (or use CDN)

## DGX deployment (later)
```bash
# On DGX, run OSRM as a persistent service
docker-compose up -d osrm
# Point frontend OSRM_BASE to DGX IP
```

## Don't touch
- Existing radius commute mode (keep it as a fallback, it's instant)
- Filter logic beyond adding the sort option
- Build pipeline (this is frontend-only + optional DGX server)
