# Feature Spec: More Cities (Bangalore, Mumbai, Hyderabad)

## User story
"I'm looking in Bangalore, not just Pune. The pipeline already works — just run it for more cities."

## What it does
Add Bangalore, Mumbai, and Hyderabad to the city dropdown. The pipeline is already city-agnostic; each city needs a crawl run and pipeline execution.

## Cities already configured
`data/cities.json` already has entries for:
```json
{
  "gurgaon": { "name": "Gurugram", "magicbricks": "gurgaon", "bbox": [28.33, 76.88, 28.55, 77.16], "center": [77.065, 28.425], "zoom": 12.4 },
  "bangalore": { "name": "Bengaluru", "magicbricks": "bangalore", "bbox": [12.80, 77.40, 13.20, 77.80], "center": [77.60, 12.97], "zoom": 11.4 },
  "mumbai": { "name": "Mumbai", "magicbricks": "mumbai", "bbox": [18.89, 72.77, 19.30, 73.05], "center": [72.88, 19.08], "zoom": 11.4 },
  "pune": { "name": "Pune", "magicbricks": "pune", "bbox": [18.40, 73.70, 18.65, 74.00], "center": [73.85, 18.52], "zoom": 11.8 }
}
```

## Pipeline execution per city

### On DGX (has the compute and bandwidth):

```bash
cd pipeline

# === BANGALORE ===
python mb_crawl.py list bangalore          # ~30 min, get project listing
python mb_crawl.py projects bangalore      # ~8-12 hours, polite crawl
python osm_fetch.py bangalore              # ~5 min, areas + buildings + POIs
python udise_fetch.py bangalore            # ~2 min, schools from DataMeet
python aqi_fetch.py bangalore              # ~1 min, AQI stations
python build_city.py bangalore             # ~5 min, merge everything

# === MUMBAI ===
python mb_crawl.py list mumbai
python mb_crawl.py projects mumbai
python osm_fetch.py mumbai
python udise_fetch.py mumbai
python aqi_fetch.py mumbai
python build_city.py mumbai

# === HYDERABAD ===
# First, add to cities.json:
# "hyderabad": { "name": "Hyderabad", "magicbricks": "hyderabad", "bbox": [17.30, 78.30, 17.55, 78.60], "center": [78.47, 17.42], "zoom": 11.6 }
python mb_crawl.py list hyderabad
python mb_crawl.py projects hyderabad
python osm_fetch.py hyderabad
python udise_fetch.py hyderabad
python aqi_fetch.py hyderabad
python build_city.py hyderabad
```

### Expected data volumes (from Magicbricks):
- Bangalore: ~40-50k projects (India's biggest tech city)
- Mumbai: ~50-60k projects (most expensive market)
- Hyderabad: ~25-30k projects

### Run all three in parallel on DGX:
```bash
# Screen sessions or tmux panes
screen -S blr -dm bash -c "cd pipeline && python mb_crawl.py list bangalore && python mb_crawl.py projects bangalore > crawl_bangalore.log 2>&1"
screen -S mum -dm bash -c "cd pipeline && python mb_crawl.py list mumbai && python mb_crawl.py projects mumbai > crawl_mumbai.log 2>&1"
screen -S hyd -dm bash -c "cd pipeline && python mb_crawl.py list hyderabad && python mb_crawl.py projects hyderabad > crawl_hyderabad.log 2>&1"
```

**Important**: Running 3 crawlers in parallel against Magicbricks. Each crawler is polite (1 req/sec), so 3 in parallel = 3 req/sec total. This should be fine — different city URLs, well within normal browsing patterns. But if any returns 429/captcha, reduce to 2 at a time.

## Changes needed

### 1. Add Hyderabad to `data/cities.json`
```json
"hyderabad": { 
  "name": "Hyderabad", 
  "magicbricks": "hyderabad", 
  "bbox": [17.30, 78.30, 17.55, 78.60], 
  "center": [78.47, 17.42], 
  "zoom": 11.6 
}
```

### 2. UDISE DataMeet coverage
Check if DataMeet CSV covers Karnataka, Maharashtra, Telangana state codes:
- Karnataka (Bangalore): state code 29
- Maharashtra (Mumbai): state code 27 (same as Pune — should work)
- Telangana (Hyderabad): state code 36

The UDISE fetcher filters by state+district from the DataMeet extract. Verify district names match.

### 3. City-specific metro data
- **Bangalore**: Namma Metro (Purple + Green lines, ~70 stations). OSM has good coverage.
- **Mumbai**: Mumbai Metro (multiple lines), plus Mumbai Local rail network (critical — not "metro" but main commute mode). May need to handle `railway=rail` + `network=Mumbai Suburban` as metro-equivalent.
- **Hyderabad**: Hyderabad Metro (Blue, Red, Green lines). OSM coverage varies.

### 4. No code changes needed
The pipeline scripts are parameterized by city_id. The frontend loads from `cities.json` and renders whatever cities exist. No code changes required — just data generation.

### 5. Verify city-specific edge cases
- Mumbai has very narrow geography (peninsula). Bbox may need adjustment.
- Bangalore has satellite areas (Whitefield, Electronic City) that may fall outside bbox. Verify bbox covers them.
- Hyderabad includes Secunderabad (twin city). Bbox should cover both.

## Output per city
After pipeline runs, each city generates:
```
web/public/data/<city>.json         # societies + units + bhk data
web/public/data/<city>-shapes.geojson  # building outlines
web/public/data/<city>-transit.geojson # metro/rail
web/public/data/<city>-schools.geojson # schools
web/public/data/<city>-flood.geojson   # waterways
web/public/data/<city>-aqi.json        # AQI stations
web/public/data/<city>-societies.csv   # CSV export
web/public/data/<city>-units.csv       # CSV export
```

## Timeline
- Crawl: 8-12 hours per city (run on DGX overnight)
- Pipeline: 10-15 min per city after crawl
- Total: start Friday evening, all three cities ready Saturday morning

## Files to change
- `data/cities.json` — add hyderabad entry
- `pipeline/udise_fetch.py` — verify state/district code handling for new cities
- No frontend changes needed

## Don't touch
- Crawler code (already parameterized)
- Build pipeline (already parameterized)  
- Frontend (already loads from cities.json dynamically)
