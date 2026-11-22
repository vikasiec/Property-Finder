"""Quick geocode: assign approximate lat/lng to projects using locality+pincode via OSM Nominatim.

usage: python geocode_localities.py <city>
Reads out/<city>/mb_index.json, geocodes unique locality+pincode combos,
writes out/<city>/mb_projects.json with lat/lng injected.
"""
import json
import hashlib
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).parent
CACHE = ROOT / "cache" / "geo"
OUT = ROOT / "out"
CITIES = json.loads((ROOT.parent / "data" / "cities.json").read_text())
CITY = sys.argv[1] if len(sys.argv) > 1 else "gurgaon"
CFG = CITIES[CITY]
UA = "FlatFinder/0.1 (housing search tool)"
DELAY = 1.1


def geocode(query):
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(query.encode()).hexdigest()
    f = CACHE / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text())
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.request.quote(query)}&format=json&limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        resp = urllib.request.urlopen(req, timeout=15).read().decode()
        results = json.loads(resp)
        result = results[0] if results else None
        f.write_text(json.dumps(result))
        time.sleep(DELAY)
        return result
    except Exception as e:
        print(f"  geocode failed: {query} - {e}", flush=True)
        return None


def main():
    idx_file = OUT / CITY / "mb_index.json"
    projects = json.loads(idx_file.read_text())
    print(f"Loaded {len(projects)} projects", flush=True)

    bbox = CFG["bbox"]
    city_name = CFG["name"]

    # collect unique locality+pincode combos
    combos = {}
    for p in projects:
        loc = p.get("locality") or ""
        pin = p.get("pincode") or ""
        key = f"{loc}|{pin}"
        if key not in combos:
            combos[key] = (loc, pin)

    print(f"Unique locality+pincode combos: {len(combos)}", flush=True)

    # geocode each combo
    coords = {}
    for i, (key, (loc, pin)) in enumerate(combos.items(), 1):
        query = f"{loc}, {city_name}, India"
        if pin:
            query = f"{loc}, {pin}, India"
        result = geocode(query)
        if result:
            lat, lng = float(result["lat"]), float(result["lon"])
            if bbox[0] < lat < bbox[2] and bbox[1] < lng < bbox[3]:
                coords[key] = (lat, lng)
            else:
                # try without pincode
                if pin:
                    result2 = geocode(f"{loc}, {city_name}, India")
                    if result2:
                        lat2, lng2 = float(result2["lat"]), float(result2["lon"])
                        if bbox[0] < lat2 < bbox[2] and bbox[1] < lng2 < bbox[3]:
                            coords[key] = (lat2, lng2)
        if i % 50 == 0 or i == len(combos):
            print(f"geocoded {i}/{len(combos)}, located {len(coords)}", flush=True)

    # inject coordinates into projects
    located = 0
    for p in projects:
        key = f"{p.get('locality') or ''}|{p.get('pincode') or ''}"
        if key in coords:
            p["lat"], p["lng"] = coords[key]
            located += 1

    print(f"Located {located}/{len(projects)} projects", flush=True)

    # write as mb_projects.json so build_city.py can consume it
    out_dir = OUT / CITY
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mb_projects.json").write_text(json.dumps(projects, indent=0))
    print(f"Wrote {out_dir / 'mb_projects.json'}", flush=True)


if __name__ == "__main__":
    main()
