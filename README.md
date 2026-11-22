# Flat Finder

Every housing society in a city on one night map. Set the smallest bedroom you can live with, size, BHK, amenities and budget, and watch the societies that fit light up. Every number links to where it came from.

## Cities

- **Gurugram**: ~2,700 societies from Magicbricks, building outlines from OpenStreetMap, 564 societies with floor plans read from brochures and HRERA filings.
- **Pune**: ~29,000 societies from Magicbricks, 2,826 schools (OSM + UDISE+), metro routes, rivers, AQI stations.

## What the colours mean

- **Bright**: matches your search.
- **Amber**: likely. The rooms we have read pass, but not every bedroom has been read yet.
- **Faint outline**: not checked yet. We have no room sizes for it, so it is neither a pass nor a fail.
- **Dark**: does not match.

Building shapes come from OpenStreetMap where they are mapped. Where they are not, towers are drawn from the listed tower count and say "approximate shape" on the card. Shapes are visual only; data numbers are never estimated.

## Map layers

### Colour by

Switch between views in the layers panel:

- **Price ₹/sqft**: green (affordable) to red (expensive), 5th–95th percentile range.
- **Rental yield %**: annual gross yield (rent × 12 / price). Societies with real buy+rent listings shown at full opacity; estimated yields (from locality or city medians) shown faded. City-wide median ~3.8% for Pune, ~2.5% for Gurugram.
- **Walk score**: 0–100 composite from proximity to parks, metro/rail, schools, hospitals and shopping.
- **Supply pipeline**: Ready to Move (green), by 2027 (orange), 2028+ (red), year unknown (grey).

### Overlays

- **Metro routes**: lines and stations from OpenStreetMap transit data.
- **Schools**: from OpenStreetMap (amenity=school, kindergarten, college, university) merged with UDISE+ DataMeet extract. Pune has 2,826 schools; Gurugram uses OSM only.
- **Rivers & flood risk**: waterways with a buffer zone showing flood-prone areas.
- **Air quality**: AQI monitoring stations with colour-coded readings.

## How bedroom sizes are read

Four sources, most trusted first. Each unit on a card says which one it came from.

1. **Checked by hand**: rooms read from builder brochures or HRERA plans by a person, page cited (`data/verified/<city>.json`).
2. **OCR of a floor plan image**: macOS's built-in text recognition reads every printed size on the plan; code pairs each size with its own room label and takes the smallest bedroom. Free and local (`pipeline/plan_ocr.py`). Where Jev also read the plan, the two must agree within 2 inches.
3. **OCR of brochures and HRERA filings**: the same reading on brochure pages and HRERA "approved building plans" (`pipeline/brochure_ocr.py`, `pipeline/hrera.py`). A page can hold two unit plans, so these are never "complete": a failing room still fails, passing rooms only make a society "likely".
4. **Jev (TypeSafe)**: a fast typed-decision model that answers multiple-choice and yes/no questions about the plan image (`pipeline/jev_reader.py`). Used as a cross-check and a fallback. In spot checks it overstated a room about 1 time in 10, so a Jev-only reading is never more than "likely".

Bedrooms under 8 ft wide are dropped as mis-pairings. Plans that are 3D renders without printed sizes are skipped.

## Buy or rent

Every society shows buy prices and monthly rents per BHK: medians, ranges and counts of live Magicbricks listings. Where a society has no listings, the site shows **our estimate, marked "~"**, with the working shown:

- rent from price (or price from rent) using the rental yield measured on societies that have both buy and rent listings for the same BHK, using the locality's own yield where it has at least 4 pairs;
- when there are no listings at all, unit size × the project's price per sq ft, then rent via yield.

Listing medians that look like typos (far from the locality median, impossible yield, or wild price per sq ft) are flagged with a reason and shown but not used for filtering, sorting or estimates.

Cards also show resident ratings by category, review snippets, the 5-year price per sq ft trend, and links to Google Maps and directions.

## Download the data

- `/data/<city>-societies.csv`: one row per society (location, type, listings, buy and rent medians and estimates per BHK, ratings, amenities, links).
- `/data/<city>-units.csv`: one row per unit type, with bedroom sizes and sources.
- "Export these results" on the site downloads whatever your filters currently match.

Generated data files are not in the repo. Rebuild them with the pipeline (see below), or download the data zip from Google Drive (link in the project).

## Use it inside Claude (connector)

Flat Finder is an MCP server at `https://flat-finder.pages.dev/mcp`. In Claude, add a custom connector with that URL, then ask things like "3 BHK in Pune under ₹1.5 Cr, every bedroom at least 11 by 12, school within 1 km". Tools: `search_societies`, `breakdown`, `list_localities`, `get_society`, `compare_societies`.

## Run it

```bash
# crawl (polite, cached, resumable — takes hours for a full city)
cd pipeline
python mb_crawl.py list pune && python mb_crawl.py projects pune
python osm_fetch.py pune          # areas, buildings, POIs, transit, waterways
python udise_fetch.py pune        # school data from UDISE+ / DataMeet
python aqi_fetch.py pune          # air quality stations
python build_city.py pune         # merges everything -> web/public/data/

# site
cd ../web && npm install && npm run dev
```

Tests: `cd pipeline && uv run --with pytest pytest` and `cd web && npx vitest run --root .. cli web/src`.

Cities live in `data/cities.json`. Switch cities with the dropdown or `?city=pune`.

URL parameters: `?city=pune`, `?map=streets` or `?map=light`, `?open=<society id>` opens one society, `?nointro` skips the globe fly-in.

## Data pipeline

```
mb_crawl.py      Magicbricks list + project pages -> out/<city>/mb_projects.json
na_crawl.py      99acres list + project pages -> out/<city>/na_projects.json
osm_fetch.py     Overpass API -> areas, buildings, POIs, transit, waterways
udise_fetch.py   UDISE+ schools (DataMeet fallback) -> out/<city>/udise_schools.json
aqi_fetch.py     CPCB/WAQI air quality stations -> out/<city>/aqi.json
build_city.py    Merge all sources -> web/public/data/<city>.json + CSVs + GeoJSON
```

Each crawler is cached and resumable. Delete files under `pipeline/cache/` to force a re-fetch.

## Add verified research

Verified rows live in `data/verified/<city>.json`. Each unit type lists its bedrooms exactly as printed (`12'10"x16'4"` or millimetres `3350x3750`) with the source URL and page. Open a pull request, or use "Research this society" on any card to request one.

## Sources

Magicbricks project pages (listing facts, live sale and rent listings, resident ratings and reviews), 99acres project pages, OpenStreetMap contributors (outlines, POIs, transit, ODbL), UDISE+ / DataMeet (school directory), CPCB/WAQI (air quality), Esri World Imagery (basemap), OpenFreeMap (roads and city buildings), HRERA Gurugram and builder brochures (verified rows).
