"""Society scores that can be derived from a city file we already have.

Liquidity, builder delivery, price-trend percent, and similar localities
use the published society fields. Noise uses a noise GeoJSON when one exists.
Crime counts are not estimated here.
"""
import json
import math
import pathlib
import statistics

import geo

ROOT = pathlib.Path(__file__).parent
WEB = ROOT.parent / "web" / "public" / "data"
OUT = ROOT / "out"

RERA_HOME = {
    "pune": "https://maharera.maharashtra.gov.in/",
    "mumbai": "https://maharera.maharashtra.gov.in/",
    "gurgaon": "https://haryanarera.gov.in/",
    "bangalore": "https://rera.karnataka.gov.in/",
    "hyderabad": "https://rera.telangana.gov.in/",
}

# Pune Airport (Lohegaon): centre, runway bearing, length in metres.
PUNE_RUNWAY = (18.5822, 73.9197, 100, 2500)


def _ready(society):
    return "ready" in (society.get("status") or "").lower()


def calc_liquidity_score(society, locality_stats):
    """Single-snapshot liquidity. Turnover needs later crawls."""
    score = 50
    sales = society.get("sale_count") or 0
    if sales >= 5:
        score += 15
    elif sales >= 2:
        score += 8
    if sales > 30:
        score -= 10
    rents = society.get("rent_count") or 0
    if rents >= 3:
        score += 10
    if rents >= 10:
        score += 5
    lo, hi = society.get("price_min"), society.get("price_max")
    if lo and hi and lo > 0:
        spread = (hi - lo) / lo
        if spread < 0.3:
            score += 10
        elif spread > 1.0:
            score -= 10
    yld = society.get("rental_yield")
    if yld and yld > 4:
        score += 10
    elif yld and yld > 3:
        score += 5
    loc_listings = locality_stats.get(society.get("locality") or "", {}).get("total_listings", 0)
    if loc_listings > 100:
        score += 10
    elif loc_listings > 50:
        score += 5
    record = society.get("builder_record") or {}
    if record.get("total", 0) > 5:
        score += 5
    if _ready(society):
        score += 5
    return max(0, min(100, score))


def liquidity_label(score):
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def add_builder_records(societies, city_id):
    by_dev = {}
    for society in societies:
        name = (society.get("developer") or "").strip()
        if name:
            by_dev.setdefault(name, []).append(society)
    records = {}
    for name, projects in by_dev.items():
        delivered = sum(1 for project in projects if _ready(project))
        records[name] = {
            "total": len(projects),
            "delivered": delivered,
            "delivery_pct": round(delivered / len(projects) * 100),
            "avg_delay": None,
        }
    home = RERA_HOME.get(city_id)
    for society in societies:
        record = records.get((society.get("developer") or "").strip())
        if record:
            society["builder_record"] = record
        if society.get("rera_id") and home:
            society["rera_link"] = home


def add_liquidity_scores(societies):
    stats = {}
    for society in societies:
        loc = society.get("locality") or ""
        bucket = stats.setdefault(loc, {"total_listings": 0})
        bucket["total_listings"] += (society.get("sale_count") or 0) + (society.get("rent_count") or 0)
    for society in societies:
        score = calc_liquidity_score(society, stats)
        society["liquidity_score"] = score
        society["liquidity_label"] = liquidity_label(score)


def trend_values(trend):
    vals = []
    for point in trend or []:
        if isinstance(point, (list, tuple)) and len(point) >= 2 and point[1]:
            vals.append(float(point[1]))
        elif isinstance(point, dict) and point.get("psf"):
            vals.append(float(point["psf"]))
    return vals


def trend_pct(trend):
    vals = trend_values(trend)
    if len(vals) < 2 or not vals[0]:
        return None
    return round((vals[-1] - vals[0]) / vals[0] * 100, 1)


def _median(nums):
    nums = [n for n in nums if n is not None]
    if not nums:
        return None
    return statistics.median(nums)


def _near(society, kind, metres):
    hit = (society.get("nearby") or {}).get(kind) or {}
    return (hit.get("m") or 99999) < metres


def similar_localities(societies, min_count=8):
    """Top 5 localities with a similar profile, cheapest difference included."""
    groups = {}
    for society in societies:
        loc = (society.get("locality") or "").strip()
        if loc:
            groups.setdefault(loc, []).append(society)
    profiles = []
    for name, rows in groups.items():
        if len(rows) < min_count:
            continue
        profiles.append({
            "name": name,
            "count": len(rows),
            "med_psf": _median([r.get("psf_now") for r in rows]),
            "med_walk_score": _median([r.get("walk_score") for r in rows]),
            "med_yield": _median([r.get("rental_yield") for r in rows]),
            "has_metro": 1 if any(_near(r, "metro", 1500) or _near(r, "rail", 1500) for r in rows) else 0,
            "has_school_near": sum(_near(r, "school", 1500) for r in rows) / len(rows),
            "has_hospital_near": sum(_near(r, "hospital", 2500) for r in rows) / len(rows),
            "has_park_near": sum(_near(r, "park", 1000) for r in rows) / len(rows),
            "med_rating": _median([r.get("rating") for r in rows]),
            "ready_pct": sum(_ready(r) for r in rows) / len(rows),
        })
    features = ["med_psf", "med_walk_score", "med_yield", "has_metro", "has_school_near",
                "has_hospital_near", "has_park_near", "med_rating", "ready_pct"]
    weights = [2, 1.5, 1, 1, 0.5, 0.5, 0.5, 1, 0.5]
    spans = {}
    for feature in features:
        vals = [p[feature] for p in profiles if p[feature] is not None]
        if not vals:
            spans[feature] = (0, 1)
        else:
            lo, hi = min(vals), max(vals)
            spans[feature] = (lo, hi if hi != lo else lo + 1)

    def norm(profile, feature):
        value = profile[feature]
        lo, hi = spans[feature]
        if value is None:
            return 0.5
        return (value - lo) / (hi - lo)

    def distance(a, b):
        return math.sqrt(sum(w * (norm(a, f) - norm(b, f)) ** 2 for f, w in zip(features, weights)))

    out = {}
    for profile in profiles:
        if not profile["med_psf"]:
            continue
        ranked = sorted((other for other in profiles if other["name"] != profile["name"] and other["med_psf"]),
                        key=lambda other: distance(profile, other))
        out[profile["name"]] = [{
            "name": other["name"],
            "score": max(0, min(100, round(100 - distance(profile, other) * 10))),
            "med_psf": round(other["med_psf"]),
            "count": other["count"],
            "diff_psf_pct": round((other["med_psf"] - profile["med_psf"]) / profile["med_psf"] * 100),
        } for other in ranked[:5]]
    return out


def _destination(lng, lat, bearing_deg, metres):
    bearing = math.radians(bearing_deg)
    return (
        lng + math.sin(bearing) * metres / geo.m_per_deg_lng(lat),
        lat + math.cos(bearing) * metres / geo.M_PER_DEG_LAT,
    )


def flight_cones(lat, lng, bearing, length_m=2500, cone_m=3000, far_m=2000):
    """Two approach cones from the ends of one runway."""
    half = length_m / 2
    west = _destination(lng, lat, (bearing + 180) % 360, half)
    east = _destination(lng, lat, bearing, half)
    features = []
    for end, direction, label in ((west, (bearing + 180) % 360, "west"), (east, bearing, "east")):
        left, right = (direction - 90) % 360, (direction + 90) % 360
        near_l = _destination(*end, left, 30)
        near_r = _destination(*end, right, 30)
        far = _destination(*end, direction, cone_m)
        far_l = _destination(*far, left, far_m / 2)
        far_r = _destination(*far, right, far_m / 2)
        ring = [list(near_l), list(far_l), list(far_r), list(near_r), list(near_l)]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"type": "flight_path", "name": f"Pune Airport approach {label}", "noise_level": "high"},
        })
    return features


def _dist_polygon_m(lng, lat, ring):
    if geo.point_in_ring((lng, lat), ring):
        return 0
    best = float("inf")
    for a, b in zip(ring, ring[1:]):
        best = min(best, _dist_segment_m((lng, lat), a, b))
    return best


def _dist_segment_m(pt, a, b):
    lat = (a[1] + b[1]) / 2
    bx = (b[0] - a[0]) * geo.m_per_deg_lng(lat)
    by = (b[1] - a[1]) * geo.M_PER_DEG_LAT
    px = (pt[0] - a[0]) * geo.m_per_deg_lng(lat)
    py = (pt[1] - a[1]) * geo.M_PER_DEG_LAT
    length2 = bx * bx + by * by
    if length2 == 0:
        return geo.dist_m(pt, a)
    t = max(0.0, min(1.0, (px * bx + py * by) / length2))
    proj = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return geo.dist_m(pt, proj)


def _line_score(kind, metres):
    if kind == "flight_path":
        if metres < 500:
            return 95
        if metres < 1000:
            return 80
        if metres < 2000:
            return 60
    elif kind == "highway":
        if metres < 50:
            return 85
        if metres < 100:
            return 65
        if metres < 200:
            return 40
    elif kind == "railway":
        if metres < 50:
            return 70
        if metres < 100:
            return 50
    return 0


def add_noise_scores(societies, features):
    flights = []
    segments = []
    for feature in features:
        props = feature.get("properties") or {}
        kind = props.get("type")
        geom = feature.get("geometry") or {}
        if kind == "flight_path" and geom.get("type") == "Polygon":
            flights.append(geom["coordinates"][0])
        elif kind in ("highway", "railway") and geom.get("type") == "LineString":
            for a, b in zip(geom["coordinates"], geom["coordinates"][1:]):
                segments.append((kind, a, b))
    cell = 0.002  # about 200 m
    grid = {}
    for kind, a, b in segments:
        keys = {(round(a[0] / cell), round(a[1] / cell)), (round(b[0] / cell), round(b[1] / cell))}
        for key in keys:
            grid.setdefault(key, []).append((kind, a, b))
    labels = {"flight_path": "flight path", "highway": "highway", "railway": "railway"}
    for society in societies:
        lng, lat = society.get("lng"), society.get("lat")
        if lng is None or lat is None:
            continue
        best, source = 0, None
        for ring in flights:
            score = _line_score("flight_path", _dist_polygon_m(lng, lat, ring))
            if score > best:
                best, source = score, "flight_path"
        cx, cy = round(lng / cell), round(lat / cell)
        seen = set()
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for kind, a, b in grid.get((cx + dx, cy + dy), ()):
                    mark = (kind, a[0], a[1], b[0], b[1])
                    if mark in seen:
                        continue
                    seen.add(mark)
                    score = _line_score(kind, _dist_segment_m((lng, lat), a, b))
                    if score > best:
                        best, source = score, kind
        society["noise_score"] = best
        if source and best >= 40:
            society["noise_source"] = labels[source]


def attach(societies, city_id, trend_by_id=None, noise_features=None):
    add_builder_records(societies, city_id)
    add_liquidity_scores(societies)
    for society in societies:
        trend = (trend_by_id or {}).get(society["id"])
        if trend:
            pct = trend_pct(trend)
            if pct is not None:
                society["trend_pct"] = pct
    if noise_features:
        add_noise_scores(societies, noise_features)
    return similar_localities(societies)


def pune_flight_collection():
    lat, lng, bearing, length = PUNE_RUNWAY
    return {"type": "FeatureCollection", "features": flight_cones(lat, lng, bearing, length)}


def publish(city):
    """Stamp scores onto the published city file without rebuilding shapes."""
    path = WEB / f"{city}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    details_path = WEB / f"{city}-details.json"
    trends = {}
    if details_path.exists():
        details = json.loads(details_path.read_text(encoding="utf-8"))
        trends = {sid: row.get("trend") for sid, row in details.items() if row.get("trend")}
    noise_path = OUT / city / "noise.geojson"
    if city == "pune" and not noise_path.exists():
        noise_path.parent.mkdir(parents=True, exist_ok=True)
        noise_path.write_text(json.dumps(pune_flight_collection(), separators=(",", ":")), encoding="utf-8")
    features = []
    if noise_path.exists():
        features = json.loads(noise_path.read_text(encoding="utf-8")).get("features") or []
        web_noise = WEB / f"{city}-noise.geojson"
        web_noise.write_text(noise_path.read_text(encoding="utf-8"), encoding="utf-8")
    doc["similar_localities"] = attach(doc["societies"], city, trends, features)
    if "noise" not in doc.get("overlays", []) and features:
        doc.setdefault("overlays", []).append("noise")
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    scored = sum(1 for s in doc["societies"] if s.get("liquidity_score") is not None)
    print(f"{city}: liquidity on {scored}, similar localities {len(doc['similar_localities'])}, noise features {len(features)}")


if __name__ == "__main__":
    import sys
    publish(sys.argv[1] if len(sys.argv) > 1 else "pune")
