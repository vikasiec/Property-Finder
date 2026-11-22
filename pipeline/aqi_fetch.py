"""Fetch AQI data from CPCB for a city bbox.

usage: python aqi_fetch.py <city>  -> out/<city>/aqi.json
"""
import json
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "out"
CITIES = json.loads((ROOT.parent / "data" / "cities.json").read_text())
CITY = next((a for a in sys.argv[1:] if a in CITIES), "gurgaon")
CFG = CITIES[CITY]
BBOX = CFG["bbox"]  # south, west, north, east

# The summary JSON named in the enrichment plan now 404s. CPCB publishes the same
# station list, with coordinates and the current index, on this feed.
CPCB_URLS = [
    "https://airquality.cpcb.gov.in/caaqms/iit_rss_feed_with_coordinates",
    "https://app.cpcbccr.com/ccr_docs/caaqm/caaqm_data/caaqm_aqi_summary.json",
]


def iter_stations(payload):
    """Flatten either a station list or CPCB's country/state/city feed."""
    if isinstance(payload, list):
        yield from payload
        return
    if not isinstance(payload, dict):
        return
    country = payload.get("country")
    if isinstance(country, list):
        for state in country:
            for city in state.get("citiesInState") or []:
                for st in city.get("stationsInCity") or []:
                    row = dict(st)
                    row.setdefault("city", city.get("cityId"))
                    yield row
        return
    for key in ("stations", "data", "records"):
        if isinstance(payload.get(key), list):
            yield from payload[key]
            return


def station_record(st):
    try:
        lat = float(st.get("latitude") or st.get("lat") or 0)
        lng = float(st.get("longitude") or st.get("lng") or 0)
        aqi = int(float(st.get("airQualityIndexValue") or st.get("cur_aqi") or st.get("aqi") or 0))
    except (ValueError, TypeError):
        return None
    if aqi <= 0:
        return None
    return {
        "name": st.get("station_name") or st.get("stationName") or st.get("city") or "Unknown",
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        "aqi": aqi,
        "category": st.get("category") or aqi_category(aqi),
        "timestamp": st.get("last_update") or st.get("lastUpdate") or st.get("date_time"),
    }


def stations_in_bbox(payload, bbox):
    s, w, n, e = bbox
    out = []
    for st in iter_stations(payload):
        row = station_record(st)
        if row and s <= row["lat"] <= n and w <= row["lng"] <= e:
            out.append(row)
    return out


def fetch_aqi():
    out_dir = OUT / CITY
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / "aqi.json"
    # skip if cached less than 1 hour ago
    if cache.exists() and (time.time() - cache.stat().st_mtime) < 3600:
        print("AQI cache fresh, skipping")
        return json.loads(cache.read_text())

    stations = None
    for url in CPCB_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "flat-finder/0.1"})
            raw = urllib.request.urlopen(req, timeout=60).read()
            stations = stations_in_bbox(json.loads(raw), BBOX)
            print("AQI source", url)
            break
        except Exception as e:
            print(f"CPCB fetch failed ({url}): {e}")
    if stations is None:
        return json.loads(cache.read_text()) if cache.exists() else []

    cache.write_text(json.dumps(stations, indent=2))
    print(f"AQI stations in bbox: {len(stations)}")
    return stations


def aqi_category(aqi):
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Satisfactory"
    if aqi <= 200:
        return "Moderate"
    if aqi <= 300:
        return "Poor"
    if aqi <= 400:
        return "Very Poor"
    return "Severe"


if __name__ == "__main__":
    fetch_aqi()
