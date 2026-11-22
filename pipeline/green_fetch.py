"""Greenery score from mapped parks, woods, and grass within 500 m.

OpenStreetMap land use only. A missing polygon means it was not mapped,
not that the ground is concrete. This is not a satellite NDVI score.

usage: python green_fetch.py <city>
"""
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import geo

ROOT = Path(__file__).parent
CITIES = json.loads((ROOT.parent / "data" / "cities.json").read_text(encoding="utf-8"))
OUT = ROOT / "out"
WEB = ROOT.parent / "web" / "public" / "data"

GREEN_QUERY = """
[out:json][timeout:90][bbox:{s},{w},{n},{e}];
(
  way["landuse"~"^(forest|grass|meadow|orchard|farmland|vineyard|allotments)$"];
  way["leisure"~"^(park|garden|nature_reserve|golf_course)$"];
  way["natural"~"^(wood|scrub|grassland|heath)$"];
  relation["landuse"~"^(forest|grass|meadow|orchard|farmland)$"];
  relation["leisure"~"^(park|garden|nature_reserve)$"];
  relation["natural"~"^(wood|scrub|grassland)$"];
);
out geom;
"""


def polygon_area_m2(coords):
    if len(coords) < 3:
        return 0
    lat0 = coords[0][1]
    mx = geo.m_per_deg_lng(lat0)
    my = geo.M_PER_DEG_LAT
    area = 0
    for i, (x1, y1) in enumerate(coords):
        x2, y2 = coords[(i + 1) % len(coords)]
        area += (x1 * mx) * (y2 * my) - (x2 * mx) * (y1 * my)
    return abs(area) / 2


def point_in_circle(px, py, cx, cy, radius_m):
    dx = (px - cx) * geo.m_per_deg_lng((py + cy) / 2)
    dy = (py - cy) * geo.M_PER_DEG_LAT
    return dx * dx + dy * dy <= radius_m * radius_m


def fetch_green_polygons(bbox):
    south, west, north, east = bbox
    query = GREEN_QUERY.format(s=south, w=west, n=north, e=east)
    body = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=body,
        headers={"User-Agent": "flat-finder/0.1 (greenery)", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    polygons = []
    for el in payload.get("elements") or []:
        geom = el.get("geometry")
        if not geom or not isinstance(geom, list) or not geom or "lon" not in geom[0]:
            continue
        coords = [(p["lon"], p["lat"]) for p in geom]
        if len(coords) < 3:
            continue
        tags = el.get("tags") or {}
        kind = tags.get("landuse") or tags.get("leisure") or tags.get("natural") or "green"
        area = polygon_area_m2(coords)
        if area < 100:
            continue
        polygons.append({
            "coords": coords,
            "centroid": (sum(c[0] for c in coords) / len(coords), sum(c[1] for c in coords) / len(coords)),
            "area_m2": area,
            "kind": kind,
        })
    return polygons


def score_from_area(green_m2, radius_m=500):
    circle = math.pi * radius_m * radius_m
    fraction = min(green_m2 / circle, 0.5) if circle else 0
    breakpoints = [(0.02, 0), (0.05, 25), (0.10, 50), (0.20, 75), (0.40, 100)]
    if fraction <= breakpoints[0][0]:
        return 0
    for i in range(1, len(breakpoints)):
        f1, s1 = breakpoints[i - 1]
        f2, s2 = breakpoints[i]
        if fraction <= f2:
            return round(s1 + (fraction - f1) / (f2 - f1) * (s2 - s1))
    return 100


def label_from_score(score):
    if score >= 75:
        return "Lush"
    if score >= 50:
        return "Moderate"
    if score >= 25:
        return "Sparse"
    return "Concrete"


def publish(city, greenery):
    path = WEB / f"{city}.json"
    if not path.exists():
        return
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = greenery.get("societies") or {}
    stamped = 0
    for society in doc["societies"]:
        row = rows.get(society.get("id"))
        if not row:
            continue
        society["green_score"] = row["score"]
        society["green_label"] = row["label"]
        stamped += 1
    if "green" not in doc.get("overlays", []):
        doc.setdefault("overlays", []).append("green")
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"stamped greenery on {stamped} societies")


def fetch(city):
    if city not in CITIES:
        raise SystemExit(f"unknown city {city}")
    city_json = WEB / f"{city}.json"
    if not city_json.exists():
        raise SystemExit(f"build {city} first: {city_json} not found")
    data = json.loads(city_json.read_text(encoding="utf-8"))
    print(f"fetching green polygons for {city}...", flush=True)
    polygons = fetch_green_polygons(CITIES[city]["bbox"])
    print(f"  {len(polygons)} green polygons", flush=True)
    grid = {}
    cell = 0.005
    for poly in polygons:
        cx, cy = poly["centroid"]
        key = (round(cy / cell), round(cx / cell))
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                grid.setdefault((key[0] + dy, key[1] + dx), []).append(poly)
    results = {}
    for society in data["societies"]:
        lat, lng = society.get("lat"), society.get("lng")
        if not lat or not lng:
            continue
        nearby = grid.get((round(lat / cell), round(lng / cell)), [])
        green_m2 = 0
        near_n = 0
        for poly in nearby:
            cx, cy = poly["centroid"]
            if point_in_circle(cx, cy, lng, lat, 500):
                green_m2 += poly["area_m2"]
                near_n += 1
        score = score_from_area(green_m2)
        results[society["id"]] = {
            "score": score,
            "label": label_from_score(score),
            "green_m2": round(green_m2),
            "nearby_green": near_n,
        }
    loc_scores = {}
    for society in data["societies"]:
        loc = (society.get("locality") or "").strip()
        row = results.get(society.get("id"))
        if loc and row:
            loc_scores.setdefault(loc, []).append(row["score"])
    localities = {
        loc: {"score": round(sum(scores) / len(scores)), "label": label_from_score(round(sum(scores) / len(scores))), "count": len(scores)}
        for loc, scores in loc_scores.items()
    }
    output = {
        "city": city,
        "source": "OpenStreetMap parks, woods, and grass within 500 m. Untagged trees are not included.",
        "radius_m": 500,
        "total_green_polygons": len(polygons),
        "societies": results,
        "localities": localities,
    }
    features = []
    for poly in polygons:
        if poly["area_m2"] < 500:
            continue
        ring = [list(pt) for pt in poly["coords"]]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"kind": poly["kind"], "area_m2": round(poly["area_m2"])},
        })
    out_dir = OUT / city
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "greenery.json"
    dest.write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")
    overlay = out_dir / "green.geojson"
    overlay.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    shutil_copy = WEB / f"{city}-green.geojson"
    shutil_copy.write_text(overlay.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"greenery -> {dest} ({len(results)} societies, {len(features)} polygons)", flush=True)
    publish(city, output)


if __name__ == "__main__":
    import sys
    fetch(sys.argv[1] if len(sys.argv) > 1 else "pune")
