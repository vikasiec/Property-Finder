"""Fetch historical rainfall for each locality in a city.

Uses the Open-Meteo archive (ERA5, no key). A failed cell falls back to
the IMD monthly normal for that city, and the output says so.

usage: python rain_fetch.py <city>
Output: pipeline/out/<city>/rainfall.json and web/public/data/<city>-rainfall.json
"""
import json
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
CITIES = json.loads((ROOT.parent / "data" / "cities.json").read_text(encoding="utf-8"))
OUT = ROOT / "out"
WEB = ROOT.parent / "web" / "public" / "data"
OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"

# IMD climatological monthly normals (mm), Jan-Dec. Used only when a cell request fails.
IMD_NORMALS = {
    "pune": [2, 1, 3, 12, 25, 128, 187, 128, 120, 73, 28, 7],
    "gurgaon": [15, 18, 13, 7, 20, 52, 202, 190, 112, 15, 5, 7],
    "bangalore": [3, 7, 14, 47, 119, 81, 110, 137, 195, 155, 58, 14],
    "mumbai": [1, 1, 0, 1, 14, 574, 840, 553, 341, 76, 15, 4],
    "hyderabad": [8, 11, 15, 24, 44, 107, 165, 176, 163, 93, 24, 6],
}

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
START_YEAR = 2019
END_YEAR = 2024


def _fallback(city):
    normals = IMD_NORMALS.get(city, [0] * 12)
    annual = round(sum(normals), 1)
    return {
        "monthly_avg": normals,
        "annual_avg": annual,
        "yearly": [],
        "wettest_month": MONTH_NAMES[normals.index(max(normals))] if any(normals) else "Jul",
        "monsoon_pct": round(sum(normals[5:9]) / annual * 100) if annual else 0,
        "source": "IMD monthly normal",
    }


def fetch_cell(lat, lng, start_year=START_YEAR, end_year=END_YEAR):
    """Monthly averages and yearly totals from daily precipitation."""
    url = (f"{OPEN_METEO}?latitude={lat:.4f}&longitude={lng:.4f}"
           f"&start_date={start_year}-01-01&end_date={end_year}-12-31"
           f"&daily=precipitation_sum&timezone=Asia/Kolkata")
    req = urllib.request.Request(url, headers={"User-Agent": "flat-finder/0.1 (rainfall)"})
    resp = json.loads(urllib.request.urlopen(req, timeout=40).read())
    dates = resp["daily"]["time"]
    precip = resp["daily"]["precipitation_sum"]
    month_year = defaultdict(float)
    for date_str, mm in zip(dates, precip):
        if mm is None:
            continue
        year = int(date_str[:4])
        month = int(date_str[5:7]) - 1
        month_year[(year, month)] += mm
    monthly_avg = []
    for month in range(12):
        vals = [month_year.get((year, month), 0) for year in range(start_year, end_year + 1)]
        monthly_avg.append(round(sum(vals) / len(vals), 1))
    annual_avg = round(sum(monthly_avg), 1)
    yearly = []
    for year in range(start_year, end_year + 1):
        total = sum(month_year.get((year, month), 0) for month in range(12))
        yearly.append({"year": year, "mm": round(total, 1)})
    return {
        "monthly_avg": monthly_avg,
        "annual_avg": annual_avg,
        "yearly": yearly,
        "wettest_month": MONTH_NAMES[monthly_avg.index(max(monthly_avg))],
        "monsoon_pct": round(sum(monthly_avg[5:9]) / annual_avg * 100) if annual_avg else 0,
        "source": "Open-Meteo",
    }


def add_rainfall(societies, rainfall):
    locs = rainfall.get("localities") or {}
    stamped = 0
    for society in societies:
        loc = (society.get("locality") or "").strip()
        rain = locs.get(loc)
        if not rain:
            continue
        society["rain_annual"] = rain["annual_avg"]
        society["rain_monthly"] = rain["monthly_avg"]
        society["rain_monsoon_pct"] = rain["monsoon_pct"]
        if rain.get("yearly"):
            society["rain_yearly"] = rain["yearly"]
        stamped += 1
    return stamped


def publish(city, rainfall):
    web_path = WEB / f"{city}-rainfall.json"
    web_path.write_text(json.dumps(rainfall, separators=(",", ":")), encoding="utf-8")
    city_path = WEB / f"{city}.json"
    if not city_path.exists():
        print(f"no published {city_path}")
        return
    doc = json.loads(city_path.read_text(encoding="utf-8"))
    stamped = add_rainfall(doc["societies"], rainfall)
    if "rainfall" not in doc.get("overlays", []):
        doc.setdefault("overlays", []).append("rainfall")
    city_path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"stamped rain on {stamped} societies")


def fetch(city):
    if city not in CITIES:
        raise SystemExit(f"unknown city {city}")
    city_json = WEB / f"{city}.json"
    if not city_json.exists():
        raise SystemExit(f"build {city} first: {city_json} not found")
    data = json.loads(city_json.read_text(encoding="utf-8"))
    loc_coords = defaultdict(lambda: {"lats": [], "lngs": []})
    for society in data["societies"]:
        loc = (society.get("locality") or "").strip()
        if loc and society.get("lat") and society.get("lng"):
            loc_coords[loc]["lats"].append(society["lat"])
            loc_coords[loc]["lngs"].append(society["lng"])
    localities = {}
    for loc, coords in loc_coords.items():
        localities[loc] = {
            "lat": round(sum(coords["lats"]) / len(coords["lats"]), 4),
            "lng": round(sum(coords["lngs"]) / len(coords["lngs"]), 4),
        }
    grid = {}
    loc_to_grid = {}
    for loc, pos in localities.items():
        key = (round(pos["lat"] / 0.02) * 0.02, round(pos["lng"] / 0.02) * 0.02)
        grid.setdefault(key, []).append(loc)
        loc_to_grid[loc] = key
    print(f"{len(localities)} localities, {len(grid)} grid cells", flush=True)

    cache_path = ROOT / "cache" / "rain" / f"{city}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    grid_data = {}
    for i, key in enumerate(grid):
        cache_key = f"{key[0]:.2f},{key[1]:.2f}"
        if cache_key in cache and cache[cache_key].get("source") == "Open-Meteo":
            grid_data[key] = cache[cache_key]
            continue
        rain = None
        for attempt in range(3):
            try:
                rain = fetch_cell(key[0], key[1])
                break
            except Exception as exc:
                print(f"  {i + 1}/{len(grid)} retry {attempt + 1}: {exc}", flush=True)
                time.sleep(2 + attempt * 2)
        if rain is None:
            print(f"  {i + 1}/{len(grid)}: FAILED, using IMD normal", flush=True)
            rain = _fallback(city)
        else:
            names = ", ".join(grid[key][:3])
            print(f"  {i + 1}/{len(grid)}: {key[0]:.2f},{key[1]:.2f} -> {rain['annual_avg']} mm ({names})", flush=True)
        grid_data[key] = rain
        cache[cache_key] = rain
        if (i + 1) % 10 == 0:
            cache_path.write_text(json.dumps(cache), encoding="utf-8")
        time.sleep(0.4)
    cache_path.write_text(json.dumps(cache), encoding="utf-8")

    result = {
        "city": city,
        "source": "Open-Meteo archive (ERA5), 2019-2024. A failed cell uses the IMD monthly normal.",
        "period": f"{START_YEAR}-{END_YEAR}",
        "month_names": MONTH_NAMES,
        "localities": {},
    }
    for loc, pos in localities.items():
        rain = grid_data.get(loc_to_grid[loc])
        if rain:
            result["localities"][loc] = {**rain, "lat": pos["lat"], "lng": pos["lng"]}
    annuals = [row["annual_avg"] for row in result["localities"].values() if row.get("annual_avg")]
    if annuals:
        result["city_avg"] = round(sum(annuals) / len(annuals), 1)
        result["city_min"] = round(min(annuals), 1)
        result["city_max"] = round(max(annuals), 1)
    dest = OUT / city / "rainfall.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    print(f"rainfall -> {dest} ({len(result['localities'])} localities)", flush=True)
    publish(city, result)
    return dest


if __name__ == "__main__":
    import sys
    fetch(sys.argv[1] if len(sys.argv) > 1 else "pune")
