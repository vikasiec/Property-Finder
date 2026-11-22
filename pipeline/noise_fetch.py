"""Noise corridors: runway approach cones plus major roads and rail from OSM.

usage: python noise_fetch.py <city>
Writes pipeline/out/<city>/noise.geojson. A failed Overpass call still
writes the known Pune runway cones.
"""
import json
import sys
import urllib.parse
import urllib.request

import scores

ROOT = scores.ROOT
OUT = scores.OUT
CITIES = json.loads((ROOT.parent / "data" / "cities.json").read_text(encoding="utf-8"))

QUERY = """
[out:json][timeout:50][bbox:{s},{w},{n},{e}];
(
  way["highway"~"^(motorway|trunk)$"];
  way["railway"="rail"];
  way["aeroway"="runway"];
);
out geom;
"""


def _ways(elements):
    features = []
    for el in elements:
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        tags = el.get("tags") or {}
        coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
        if len(coords) < 2:
            continue
        if tags.get("aeroway") == "runway":
            continue  # cones are generated from runway ends below
        if tags.get("railway"):
            kind, level = "railway", "medium"
        else:
            kind, level = "highway", "high" if tags.get("highway") == "motorway" else "medium"
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"type": kind, "name": tags.get("name") or tags.get("ref") or kind, "noise_level": level},
        })
    return features


def _runway_cones(elements):
    cones = []
    for el in elements:
        tags = el.get("tags") or {}
        if tags.get("aeroway") != "runway" or not el.get("geometry"):
            continue
        coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
        if len(coords) < 2:
            continue
        a, b = coords[0], coords[-1]
        # bearing from a to b, then cones both ways via the midpoint
        import math
        import geo
        dx = (b[0] - a[0]) * geo.m_per_deg_lng((a[1] + b[1]) / 2)
        dy = (b[1] - a[1]) * geo.M_PER_DEG_LAT
        bearing = math.degrees(math.atan2(dx, dy)) % 360
        length = math.hypot(dx, dy) or 2500
        mid_lng, mid_lat = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        cones.extend(scores.flight_cones(mid_lat, mid_lng, bearing, length))
    return cones


def fetch(city):
    if city not in CITIES:
        raise SystemExit(f"unknown city {city}")
    south, west, north, east = CITIES[city]["bbox"]
    query = QUERY.format(s=south, w=west, n=north, e=east)
    features = []
    body = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=body,
        headers={"User-Agent": "flat-finder/0.1 (noise overlay)", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=70) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        elements = payload.get("elements") or []
        features.extend(_runway_cones(elements))
        features.extend(_ways(elements))
        print(f"overpass features {len(features)}", flush=True)
    except Exception as exc:
        print(f"overpass failed: {exc}", flush=True)
    if city == "pune" and not any((f.get("properties") or {}).get("type") == "flight_path" for f in features):
        features = scores.pune_flight_collection()["features"] + features
        print("added Pune Airport approach cones", flush=True)
    dest = OUT / city / "noise.geojson"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    print(f"noise features {len(features)} -> {dest}", flush=True)
    return dest


if __name__ == "__main__":
    fetch(sys.argv[1] if len(sys.argv) > 1 else "pune")
