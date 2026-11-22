# Feature Spec: Search Along Metro Route

## User story
"I commute on the Purple Line. Show me all societies within walking distance of any station on it, with prices by station."

## What it does
1. User clicks **"Metro"** button in the topbar
2. A dropdown shows available metro lines (Purple, Aqua, Pink for Pune; Yellow, Blue etc for Gurugram)
3. User picks a line and sets a walking radius (default 1 km, range 500m–2km slider)
4. Map highlights all societies within that radius of ANY station on the selected line
5. Non-matching societies dim (same as commute mode)
6. A station-wise summary panel shows: station name, societies nearby, median price/sqft, median rent

## Current data

Transit data: `web/public/data/<city>-transit.geojson`
- 3 metro lines for Pune: Aqua (Ramwadi→Vanaz), Purple (Swargate→PCMC Bhavan), Pink (District Court→Maan)
- 46 stations total
- **Issue**: Stations have no `line` property (all show `?`). Need to fix this.

## Data fix needed

### In `pipeline/osm_fetch.py` — `fetch_transit()`
Stations need a `line` property. Fix by snapping each station point to the nearest LineString feature:

```python
def assign_stations_to_lines(features):
    """
    For each Point (station) feature, find the nearest LineString (line) feature.
    Assign the line's name to the station's 'line' property.
    
    Use perpendicular distance from station point to each line segment.
    Threshold: 200m (stations should be very close to their line).
    """
    lines = [f for f in features if f['geometry']['type'] == 'LineString']
    stations = [f for f in features if f['geometry']['type'] == 'Point']
    
    for station in stations:
        slat, slng = station['geometry']['coordinates'][1], station['geometry']['coordinates'][0]
        min_dist = float('inf')
        best_line = None
        
        for line in lines:
            coords = line['geometry']['coordinates']
            for i in range(len(coords) - 1):
                dist = point_to_segment_dist(slat, slng, 
                    coords[i][1], coords[i][0], coords[i+1][1], coords[i+1][0])
                if dist < min_dist:
                    min_dist = dist
                    best_line = line['properties'].get('name', '?')
        
        station['properties']['line'] = best_line
        station['properties']['line_colour'] = best_line_colour  # from matched line
    
    return features
```

After fix, each station feature looks like:
```json
{
  "type": "Feature",
  "geometry": {"type": "Point", "coordinates": [73.85, 18.52]},
  "properties": {
    "name": "Hinjewadi",
    "line": "Purple Line: Swargate → PCMC Bhavan",
    "line_colour": "purple"
  }
}
```

## Frontend changes

### `web/index.html`
Add Metro button to topbar:
```html
<button id="btn-metro-search" title="Search along a metro line">Metro</button>
```

Add metro search panel (after commute panel):
```html
<div class="metro-panel" id="metro-panel" hidden>
  <div class="k row">Search along metro <button class="iconbtn" id="metro-close" aria-label="Close">×</button></div>
  <div>
    <label class="k" style="font-size:11px">Metro line</label>
    <select id="metro-line-pick" aria-label="Metro line"></select>
  </div>
  <div class="k row"><span>Walking radius</span><span class="val" id="metro-radius-val">1 km</span></div>
  <input type="range" id="metro-radius" min="0.5" max="2" step="0.1" value="1">
  <div id="metro-station-table"></div>
</div>
```

### `web/src/main.js`

```javascript
let metroSearchMode = false, metroLine = null, metroRadiusKm = 1;
let transitData = null; // cached transit.geojson

async function toggleMetroSearch() {
  metroSearchMode = !metroSearchMode;
  $('btn-metro-search').classList.toggle('on', metroSearchMode);
  $('metro-panel').hidden = !metroSearchMode;
  
  // Mutually exclusive with commute mode
  if (metroSearchMode && commuteMode) {
    commuteMode = false;
    $('btn-commute').classList.remove('on');
    $('commute-panel').hidden = true;
  }
  
  if (metroSearchMode) {
    // Load transit data
    if (!transitData) {
      transitData = await fetch(`/data/${cityId}-transit.geojson`).then(r => r.json());
    }
    
    // Auto-enable metro overlay
    $('dl-metro').checked = true;
    toggleMetro();
    
    // Populate line dropdown
    const lines = transitData.features
      .filter(f => f.geometry.type === 'LineString')
      .map(f => f.properties);
    
    $('metro-line-pick').replaceChildren(
      ...lines.map(l => new Option(l.name, l.name))
    );
    
    metroLine = lines[0]?.name;
    applyMetroFilter();
  } else {
    // Clear metro filter
    apply();
  }
}

function applyMetroFilter() {
  if (!metroSearchMode || !transitData) return;
  
  // Get stations on selected line
  const stations = transitData.features
    .filter(f => f.geometry.type === 'Point' && f.properties.line === metroLine);
  
  // For each society, check distance to any station on this line
  const radiusM = metroRadiusKm * 1000;
  const stationResults = new Map(); // station_name -> {societies: [], med_psf, med_rent}
  
  data.societies.forEach(s => {
    let nearestDist = Infinity, nearestStation = null;
    
    for (const st of stations) {
      const [lng, lat] = st.geometry.coordinates;
      const dist = haversine(s.lat, s.lng, lat, lng);
      if (dist < nearestDist) {
        nearestDist = dist;
        nearestStation = st.properties.name;
      }
    }
    
    if (nearestDist <= radiusM) {
      s._metroStation = nearestStation;
      s._metroDist = Math.round(nearestDist);
      
      if (!stationResults.has(nearestStation)) {
        stationResults.set(nearestStation, { societies: [] });
      }
      stationResults.get(nearestStation).societies.push(s);
    } else {
      s._metroStation = null;
      states.set(s.id, 'no'); // dim
    }
  });
  
  // Render station breakdown table
  renderStationTable(stations, stationResults);
  
  // Highlight the selected metro line
  highlightMetroLine(metroLine);
  
  // Draw radius circles around stations
  drawStationRadii(stations, radiusM);
  
  setStates(map, states);
  updateCount();
}

function renderStationTable(stations, stationResults) {
  const bhk = crit.bhk.length ? crit.bhk[0] : 2; // default BHK for rent display
  
  const rows = stations.map(st => {
    const name = st.properties.name;
    const result = stationResults.get(name);
    if (!result) return null;
    
    const socs = result.societies;
    const psfs = socs.map(s => s.psf_now).filter(Boolean);
    const rents = socs.map(s => {
      const b = s.bhk?.[bhk];
      return b?.rent_med || b?.rent_est;
    }).filter(Boolean);
    
    return `
      <tr class="metro-st-row" data-lat="${st.geometry.coordinates[1]}" data-lng="${st.geometry.coordinates[0]}">
        <td><b>${esc(name)}</b></td>
        <td>${socs.length}</td>
        <td>${psfs.length ? '₹' + formatINR(median(psfs)) : '-'}</td>
        <td>${rents.length ? '₹' + formatINR(median(rents)) : '-'}</td>
      </tr>
    `;
  }).filter(Boolean).join('');
  
  $('metro-station-table').innerHTML = `
    <table class="metro-table">
      <thead><tr><th>Station</th><th>Nearby</th><th>₹/sqft</th><th>${bhk}BHK rent</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  
  // Click station row to fly there
  document.querySelectorAll('.metro-st-row').forEach(row => {
    row.onclick = () => {
      map.flyTo({
        center: [parseFloat(row.dataset.lng), parseFloat(row.dataset.lat)],
        zoom: 15, duration: 1500
      });
    };
  });
}

function highlightMetroLine(lineName) {
  // Thicken the selected line, fade others
  if (map.getLayer('metro-lines')) {
    map.setPaintProperty('metro-lines', 'line-width', [
      'case', ['==', ['get', 'name'], lineName], 5, 2
    ]);
    map.setPaintProperty('metro-lines', 'line-opacity', [
      'case', ['==', ['get', 'name'], lineName], 1, 0.3
    ]);
  }
}

function drawStationRadii(stations, radiusM) {
  // Draw circles around each station using turf or manual circle points
  const circles = stations.map(st => {
    const [lng, lat] = st.geometry.coordinates;
    return createCirclePolygon(lat, lng, radiusM, 32);
  });
  
  const geojson = { type: 'FeatureCollection', features: circles };
  
  if (map.getSource('metro-radii')) {
    map.getSource('metro-radii').setData(geojson);
  } else {
    map.addSource('metro-radii', { type: 'geojson', data: geojson });
    map.addLayer({
      id: 'metro-radii-fill', type: 'fill', source: 'metro-radii',
      paint: { 'fill-color': '#00bcd4', 'fill-opacity': 0.08 }
    }, 'societies');
    map.addLayer({
      id: 'metro-radii-line', type: 'line', source: 'metro-radii',
      paint: { 'line-color': '#00bcd4', 'line-width': 1.5, 'line-dasharray': [3, 2] }
    }, 'societies');
  }
}
```

### Sort option
Add "Nearest to station" when metro search is active:
```javascript
// In sort select, add dynamically when metroSearchMode:
if (metroSearchMode) {
  // Add option
}

case 'station':
  return (a._metroDist ?? 99999) - (b._metroDist ?? 99999);
```

### Card enhancement
When in metro search mode, show distance to nearest station:
```html
<div class="metro-dist">🚇 ${s._metroDist}m from ${s._metroStation}</div>
```

## Styles
```css
.metro-panel {
  position: absolute; left: 12px; bottom: 100px;
  width: 320px; padding: 12px;
  background: rgba(20,20,30,0.95); backdrop-filter: blur(12px);
  border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,0.5);
  z-index: 10;
}
.metro-table { width: 100%; font-size: 12px; border-collapse: collapse; }
.metro-table th { text-align: left; padding: 4px 6px; color: rgba(255,255,255,0.5); font-weight: 400; }
.metro-table td { padding: 6px; border-top: 1px solid rgba(255,255,255,0.08); }
.metro-st-row { cursor: pointer; }
.metro-st-row:hover { background: rgba(255,255,255,0.08); }
.metro-dist { font-size: 12px; color: #00bcd4; margin: 4px 0; }

@media (max-width: 700px) {
  .metro-panel {
    position: fixed; bottom: 0; left: 0; right: 0; width: auto;
    max-height: 50vh; overflow-y: auto;
    border-radius: 16px 16px 0 0;
    padding-bottom: env(safe-area-inset-bottom, 16px);
  }
}
```

## Wire-up
```javascript
$('btn-metro-search').onclick = toggleMetroSearch;
$('metro-close').onclick = () => { metroSearchMode = false; toggleMetroSearch(); };
$('metro-line-pick').onchange = () => { metroLine = $('metro-line-pick').value; applyMetroFilter(); };
$('metro-radius').oninput = () => {
  metroRadiusKm = parseFloat($('metro-radius').value);
  $('metro-radius-val').textContent = `${metroRadiusKm} km`;
  applyMetroFilter();
};
```

## Files to change
- `pipeline/osm_fetch.py` — fix `assign_stations_to_lines()` to add `line` property to stations
- `web/index.html` — add Metro button, metro panel HTML
- `web/src/main.js` — add metro search mode logic, station table, radius drawing
- `web/src/style.css` — metro panel and table styles

## Don't touch
- `build_city.py` — no changes needed
- Existing metro overlay toggle (auto-enables but stays independently toggleable)
- Commute mode (keep as separate feature, mutually exclusive)
- Filter logic in `filters.js`
