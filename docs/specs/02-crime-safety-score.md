# Feature Spec: Crime / Safety Score

## User story
"Is this area safe? I want to know before I visit, not after I've signed the agreement."

## What it does
Each society gets a **safety_score** (0–100, higher = safer) shown on the card and usable as a colour-by layer. Ward/zone-level crime data is the best publicly available granularity for Indian cities.

## Data sources (in priority order)

### 1. NCRB district-level data (baseline)
- National Crime Records Bureau publishes annual crime statistics per district
- Download: https://ncrb.gov.in → "Crime in India" → district-wise tables
- Format: PDF tables or Excel. Relevant metrics:
  - Total IPC crimes per 1 lakh population
  - Crimes against women
  - Theft, burglary, robbery rates
  - Murder rate
- **Limitation**: district-level only (Pune is one district). Useful as baseline comparison between cities.

### 2. Police station jurisdiction mapping
- Each police station has a geographic jurisdiction
- Maharashtra Police publishes station-wise FIR data: https://citizen.mahapolice.gov.in
- Scrape or manually compile: station name → crime count → polygon/point
- Map each society to nearest police station jurisdiction

### 3. SafetiPin / community safety data (if available)
- SafetiPin has crowd-sourced safety audit data for Indian cities
- API or web scrape for safety scores by area

### Pipeline: `pipeline/safety_fetch.py` (new file)

```python
def fetch_safety_data(city_id):
    """
    Step 1: Load NCRB district data from data/ncrb/<city>.json (manually curated)
    Step 2: Load police station locations from OSM
        Overpass: node["amenity"="police"](bbox)
    Step 3: If city-specific ward data exists in data/safety/<city>_wards.json, load it
    Step 4: Assign each ward/station a relative safety score (0-100)
        - Normalize crime rate per capita within the city
        - Invert: low crime = high safety score
    
    Output: out/<city>/safety.json
    {
        "stations": [
            {"name": "Kothrud PS", "lat": 18.50, "lng": 73.81, "score": 72, "crimes_per_lakh": 180},
            ...
        ],
        "city_avg_score": 65,
        "source": "Maharashtra Police FIR data 2024",
        "note": "Ward-level. Not all crime types weighted equally."
    }
    """
```

### Manual data curation needed
Create `data/safety/pune_wards.json`:
```json
[
  {"ward": "Kothrud", "zone": "Zone 4", "station": "Kothrud PS", 
   "lat": 18.50, "lng": 73.81,
   "ipc_total": 450, "theft": 120, "burglary": 35, "population": 250000}
]
```
This is a one-time manual effort from published PMC ward data + police annual reports.

## Integration in `build_city.py`

```python
def calc_safety_score(society, safety_data):
    """
    Find the nearest police station/ward to the society.
    Use its normalized crime rate to compute safety_score.
    
    Scoring:
    - crimes_per_lakh < 100: score 85-100 (very safe)
    - crimes_per_lakh 100-200: score 65-85 (safe)
    - crimes_per_lakh 200-400: score 40-65 (moderate)
    - crimes_per_lakh > 400: score 0-40 (concern)
    
    Weight: theft/burglary 2x, violent crime 3x, other 1x
    """
    nearest = find_nearest_station(society['lat'], society['lng'], safety_data['stations'])
    return nearest['score']  # already normalized
```

Add to each society: `"safety_score": 72, "safety_zone": "Kothrud PS"`

## Frontend changes

### Society card (`web/src/main.js`)
In the card HTML, add after ratings:
```html
<div class="safety-row">
  <span class="safety-badge safety-${level}">${score}/100</span>
  <span class="fine">Safety score · ${zone_name}</span>
</div>
```
Where `level` is "good" (>70), "moderate" (40-70), "concern" (<40).

### Colour-by mode
Add a new colour-by radio button:
```html
<label class="sw"><input type="radio" name="colorby" value="safety"> Safety score</label>
```

Colour scale: green (safe, >70) → yellow (moderate, 40-70) → red (concern, <40).

Implementation in `setColorBy()`:
```javascript
case 'safety':
  societies.forEach(s => {
    const score = s.safety_score ?? 50;
    // green (safe) to red (concern)
    const color = score > 70 ? '#4caf50' : score > 40 ? '#ff9800' : '#f44336';
    const opacity = s.safety_score != null ? 0.8 : 0.3;  // fade unknown
  });
  break;
```

### Layer legend
When safety colour-by is active, show:
```
Safe (>70) ■ Moderate (40-70) ■ Concern (<40) ■
```

## Files to create/change
- `data/safety/pune_wards.json` — NEW: manually curated ward crime data
- `pipeline/safety_fetch.py` — NEW: load + normalize safety data, fetch police stations from OSM
- `pipeline/build_city.py` — add `safety_score` and `safety_zone` to each society
- `web/index.html` — add safety colour-by radio button
- `web/src/main.js` — add safety colour-by case, add card safety badge
- `web/src/style.css` — `.safety-badge`, `.safety-good/moderate/concern` styles

## Limitations to show in UI
- "Safety scores are ward-level estimates from published police data. They reflect reported crime rates, not personal safety."
- Show source and year on the card tooltip

## Don't touch
- Existing colour-by modes
- Filter logic
- Other overlays
