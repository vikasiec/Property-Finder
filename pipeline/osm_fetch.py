"""Fetch residential areas and building footprints for a city bbox from Overpass, once.

usage: python osm_fetch.py <city>  -> out/<city>/osm_areas.geojson, out/<city>/osm_buildings.geojson
"""
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import geo

ROOT = pathlib.Path(__file__).parent
CACHE = ROOT / "cache" / "osm"
OUT = ROOT / "out"
CITIES = json.loads((ROOT.parent / "data" / "cities.json").read_text())
CITY = next((a for a in sys.argv[1:] if a in CITIES), "gurgaon")
BBOX = tuple(CITIES[CITY]["bbox"])  # south, west, north, east
OUT = OUT / CITY
CACHE = CACHE / CITY
MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


def overpass(query, name, tries=2, timeout=300, pause=10):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{name}.json"
    if f.exists():
        return json.loads(f.read_text())
    body = urllib.parse.urlencode({"data": query}).encode()
    for url in MIRRORS * tries:
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": "flat-finder/0.1"})
            raw = urllib.request.urlopen(req, timeout=timeout).read()
            data = json.loads(raw)
            els = data.get("elements") or []
            # Some mirrors answer `out geom` with tags and bounds only. That cannot draw a route.
            if name in ("transit", "waterways") and els and not any(e.get("geometry") or e.get("members") for e in els):
                print("mirror returned no geometry", url, flush=True)
                continue
            f.write_bytes(raw)
            return data
        except Exception as e:
            print("mirror failed", url, e, flush=True)
            time.sleep(pause)
    raise SystemExit("all Overpass mirrors failed")


def try_overpass(query, name):
    """One short pass. Callers that can use the OSM API continue when every mirror fails."""
    try:
        return overpass(query, name, tries=1, timeout=25, pause=2)
    except SystemExit:
        print("overpass unavailable for", name, flush=True)
        return None


def _pts(geom):
    return [(round(p["lon"], 6), round(p["lat"], 6)) for p in geom]


def ring_from_relation(el):
    """Join a multipolygon relation's outer member ways into closed rings."""
    segs = [_pts(m["geometry"]) for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
    rings = []
    while segs:
        ring = segs.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += s[::-1][1:]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring
                else:
                    continue
                segs.pop(i)
                changed = True
                break
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def height_of(tags):
    try:
        if tags.get("height"):
            return float(str(tags["height"]).split()[0])
        if tags.get("building:levels"):
            return float(tags["building:levels"]) * 3.2
    except ValueError:
        pass
    return None


def main():
    s, w, n, e = BBOX
    bb = f"({s},{w},{n},{e})"
    areas = overpass(f'[out:json][timeout:280];(way["landuse"="residential"]["name"]{bb};relation["landuse"="residential"]["name"]{bb};);out geom;', "areas")
    feats = []
    for el in areas["elements"]:
        rings = ring_from_relation(el) if el["type"] == "relation" else [_pts(el["geometry"])]
        for r in rings:
            feats.append({"type": "Feature", "properties": {"osm": f"{el['type']}/{el['id']}", "name": el["tags"]["name"]},
                          "geometry": {"type": "Polygon", "coordinates": [r]}})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "osm_areas.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print("areas", len(feats))

    blds = overpass(f'[out:json][timeout:280];way["building"]{bb};out geom;', "buildings")
    bf = []
    for el in blds["elements"]:
        if "geometry" not in el:
            continue
        r = _pts(el["geometry"])
        if r[0] != r[-1]:
            r.append(r[0])
        bf.append({"type": "Feature", "properties": {"osm": el["id"], "h": height_of(el.get("tags", {}))},
                   "geometry": {"type": "Polygon", "coordinates": [r]}})
    (OUT / "osm_buildings.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": bf}))
    print("buildings", len(bf))


POI_QUERY = """[out:json][timeout:280];(
  way["leisure"="park"]{bb};relation["leisure"="park"]{bb};node["leisure"="park"]{bb};
  node["railway"="station"]{bb};node["station"="subway"]{bb};node["railway"="halt"]{bb};
  node["amenity"="school"]{bb};way["amenity"="school"]{bb};relation["amenity"="school"]{bb};
  node["amenity"="kindergarten"]{bb};way["amenity"="kindergarten"]{bb};
  node["amenity"="college"]{bb};way["amenity"="college"]{bb};
  node["amenity"="university"]{bb};way["amenity"="university"]{bb};
  node["building"="school"]{bb};way["building"="school"]{bb};
  node["amenity"="hospital"]{bb};way["amenity"="hospital"]{bb};
  node["shop"="mall"]{bb};way["shop"="mall"]{bb};way["shop"="supermarket"]{bb};node["shop"="supermarket"]{bb};
);out center tags;"""

TRANSIT_QUERY = """[out:json][timeout:280];(
  relation["route"="subway"]{bb};
  relation["route"="light_rail"]{bb};
);out geom;"""

WATERWAY_QUERY = """[out:json][timeout:280];(
  way["waterway"="river"]{bb};
  way["waterway"="canal"]{bb};
  relation["waterway"="river"]{bb};
  way["natural"="water"]["water"="river"]{bb};
);out geom;"""


def poi_kind(t):
    if t.get("leisure") == "park":
        return "park"
    if t.get("station") == "subway" or "metro" in (t.get("name") or "").lower() or t.get("subway") == "yes":
        return "metro"
    if t.get("railway") in ("station", "halt"):
        return "rail"
    if t.get("amenity") in ("school", "kindergarten", "college", "university") or t.get("building") == "school":
        return "school"
    if t.get("amenity") == "hospital":
        return "hospital"
    if t.get("shop") in ("mall", "supermarket"):
        return "shopping"
    return None


def dedupe_pois(pois, metres=80):
    """Drop a later POI with the same kind and name within metres of an earlier one.

    A school mapped as both amenity=school and building=school lands twice, a few metres apart.
    """
    kept = []
    for p in pois:
        name = (p.get("name") or "").strip().lower()
        if name and any(
            q["k"] == p["k"] and (q.get("name") or "").strip().lower() == name
            and geo.dist_m((p["lng"], p["lat"]), (q["lng"], q["lat"])) < metres
            for q in kept
        ):
            continue
        kept.append(p)
    return kept


def norm_school_name(name):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split())


def school_names_match(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    return len(a) >= 8 and len(b) >= 8 and (a in b or b in a)


def merge_udise_schools(pois, schools, metres=100):
    """Add UDISE schools that are not the same OSM school within metres."""
    kept = [p for p in pois if p.get("k") == "school"]
    added = skipped = 0
    for school in schools:
        name = norm_school_name(school.get("name"))
        lat, lng = school.get("lat"), school.get("lng")
        if lat is None or lng is None:
            continue
        duplicate = any(
            school_names_match(name, norm_school_name(q.get("name")))
            and geo.dist_m((lng, lat), (q["lng"], q["lat"])) <= metres
            for q in kept
        )
        if duplicate:
            skipped += 1
            continue
        poi = {"k": "school", "name": school.get("name"), "lng": lng, "lat": lat}
        pois.append(poi)
        kept.append(poi)
        added += 1
    print(f"UDISE: added {added} schools, skipped {skipped} duplicates")
    return pois


def fetch_pois():
    s, w, n, e = BBOX
    data = overpass(POI_QUERY.replace("{bb}", f"({s},{w},{n},{e})"), "pois")
    out = []
    for el in data["elements"]:
        c = el.get("center") or ({"lat": el["lat"], "lon": el["lon"]} if "lat" in el else None)
        k = poi_kind(el.get("tags", {}))
        if c and k:
            out.append({"k": k, "name": el.get("tags", {}).get("name"), "lng": round(c["lon"], 5), "lat": round(c["lat"], 5)})
    out = dedupe_pois(out)
    udise_path = OUT / "udise_schools.json"
    if udise_path.exists():
        out = merge_udise_schools(out, json.loads(udise_path.read_text(encoding="utf-8")))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "osm_pois.json").write_text(json.dumps(out))
    from collections import Counter
    print("pois", Counter(p["k"] for p in out))


def lines_from_relation(el):
    """Join a route relation's member ways into continuous LineStrings."""
    segs = [_pts(m["geometry"]) for m in el.get("members", [])
            if m.get("type") == "way" and m.get("geometry")
            and m.get("role", "") not in ("stop", "platform")]
    segs = [s for s in segs if len(s) >= 2]
    lines = []
    while segs:
        line = list(segs.pop(0))
        changed = True
        while changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == line[-1]:
                    line += s[1:]
                    segs.pop(i)
                    changed = True
                    break
                elif s[-1] == line[0]:
                    line = s[:-1] + line
                    segs.pop(i)
                    changed = True
                    break
                elif s[-1] == line[-1]:
                    line += s[::-1][1:]
                    segs.pop(i)
                    changed = True
                    break
                elif s[0] == line[0]:
                    line = s[::-1][:-1] + line
                    segs.pop(i)
                    changed = True
                    break
        lines.append(line)
    return lines


def _stop_point(member):
    if "lat" in member and "lon" in member:
        return round(member["lon"], 5), round(member["lat"], 5)
    geom = member.get("geometry") or []
    if geom and "lon" in geom[0]:
        return round(geom[0]["lon"], 5), round(geom[0]["lat"], 5)
    return None


# Subway route relations Overpass listed for Pune on 2026-11-22. Used only when the
# mirrors answer without geometry, or not at all. One id per direction.
FALLBACK_TRANSIT = {
    "pune": [13916704, 13916710, 13917122, 13917123, 21871930, 21872220],
}


def osm_api(path):
    req = urllib.request.Request("https://www.openstreetmap.org/api/0.6/" + path, headers={"User-Agent": "flat-finder/0.1"})
    return urllib.request.urlopen(req, timeout=120).read()


def relation_from_osm(raw):
    """Turn an OSM /full document into the relation shape lines_from_relation expects."""
    root = ET.fromstring(raw)
    nodes = {}
    for n in root.findall("node"):
        nodes[n.get("id")] = {
            "lat": float(n.get("lat")), "lon": float(n.get("lon")),
            "tags": {t.get("k"): t.get("v") for t in n.findall("tag")},
        }
    ways = {}
    for w in root.findall("way"):
        geom = []
        for nd in w.findall("nd"):
            p = nodes.get(nd.get("ref"))
            if p:
                geom.append({"lon": p["lon"], "lat": p["lat"]})
        ways[w.get("id")] = geom
    rel = root.find("relation")
    members = []
    for m in rel.findall("member"):
        if m.get("type") == "way" and ways.get(m.get("ref")):
            members.append({"type": "way", "role": m.get("role") or "", "geometry": ways[m.get("ref")]})
        elif m.get("type") == "node" and m.get("ref") in nodes:
            p = nodes[m.get("ref")]
            members.append({"type": "node", "role": m.get("role") or "", "lat": p["lat"], "lon": p["lon"], "tags": p["tags"]})
    return {"type": "relation", "id": int(rel.get("id")), "tags": {t.get("k"): t.get("v") for t in rel.findall("tag")}, "members": members}


def way_from_osm(raw):
    root = ET.fromstring(raw)
    nodes = {n.get("id"): (float(n.get("lon")), float(n.get("lat"))) for n in root.findall("node")}
    w = root.find("way")
    coords = [nodes[nd.get("ref")] for nd in w.findall("nd") if nd.get("ref") in nodes]
    tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
    return tags, coords


def clip_parts(coords, pad=0.02):
    """Keep the runs of a line that sit in the city bbox (rivers continue past it)."""
    s, w, n, e = BBOX
    s, n, w, e = s - pad, n + pad, w - pad, e + pad
    parts, cur = [], []
    for lon, lat in coords:
        if w <= lon <= e and s <= lat <= n:
            cur.append((lon, lat))
        elif len(cur) >= 2:
            parts.append(cur)
            cur = []
        else:
            cur = []
    if len(cur) >= 2:
        parts.append(cur)
    return parts


def nominatim(query, bounded=False):
    s, w, n, e = BBOX
    params = {"format": "jsonv2", "q": query, "limit": 8}
    if bounded:
        params["viewbox"] = f"{w},{n},{e},{s}"
        params["bounded"] = 1
    req = urllib.request.Request("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "flat-finder/0.1"})
    time.sleep(1.1)
    return json.loads(urllib.request.urlopen(req, timeout=40).read())


def fetch_transit():
    s, w, n, e = BBOX
    bb = f"({s},{w},{n},{e})"
    data = try_overpass(TRANSIT_QUERY.replace("{bb}", bb), "transit")
    elements = list((data or {}).get("elements") or [])
    if not any(el.get("members") for el in elements):
        ids = [el["id"] for el in elements if el.get("type") == "relation"] or FALLBACK_TRANSIT.get(CITY, [])
        elements = []
        for rid in ids:
            print("osm relation", rid, flush=True)
            elements.append(relation_from_osm(osm_api(f"relation/{rid}/full")))
            time.sleep(0.4)
    feats = []
    seen_refs = set()
    for el in elements:
        tags = el.get("tags", {})
        ref = tags.get("ref") or tags.get("name") or str(el["id"])
        if ref in seen_refs:
            continue  # skip reverse-direction duplicate
        seen_refs.add(ref)
        colour = tags.get("colour") or tags.get("color") or "#8fb4ff"
        name = tags.get("name") or ref
        for line in lines_from_relation(el):
            if len(line) < 5:
                continue  # a platform stub, not the route
            feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": line},
                          "properties": {"name": name, "ref": ref, "colour": colour}})
        for m in el.get("members", []):
            if m.get("role") not in ("stop", "stop_entry_only", "stop_exit_only"):
                continue
            pt = _stop_point(m)
            if not pt:
                continue
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(pt)},
                          "properties": {"name": (m.get("tags") or {}).get("name") or "Stop", "colour": colour, "role": "stop"}})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "transit.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print("transit features", len(feats))


def fetch_waterways():
    s, w, n, e = BBOX
    bb = f"({s},{w},{n},{e})"
    data = try_overpass(WATERWAY_QUERY.replace("{bb}", bb), "waterways")
    feats = []
    if data and data.get("elements"):
        _water_features(data["elements"], feats)
    else:
        seen = set()
        city = CITIES[CITY]["name"]
        hits = []
        for q, bounded in (("river", True), ("canal", True), (f"river {city}", False)):
            try:
                hits.extend(nominatim(q, bounded))
            except Exception as e:
                print("nominatim failed", q, e, flush=True)
        for hit in hits:
            if hit.get("type") not in ("river", "canal", "stream"):
                continue
            key = (hit.get("osm_type"), hit.get("osm_id"))
            if key in seen or key[0] not in ("relation", "way"):
                continue
            seen.add(key)
            print("osm water", key, flush=True)
            try:
                if key[0] == "relation":
                    el = relation_from_osm(osm_api(f"relation/{key[1]}/full"))
                    name = (el.get("tags") or {}).get("name") or "water"
                    for line in lines_from_relation(el):
                        for part in clip_parts(line):
                            feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": part},
                                          "properties": {"name": name}})
                else:
                    tags, coords = way_from_osm(osm_api(f"way/{key[1]}/full"))
                    name = tags.get("name") or tags.get("waterway") or "water"
                    for part in clip_parts(coords):
                        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": part},
                                      "properties": {"name": name}})
            except Exception as e:
                print("water fetch failed", key, e, flush=True)
            time.sleep(0.4)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "waterways.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print("waterways", len(feats))


def _water_features(elements, feats):
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("waterway") or "water"
        if el["type"] == "way" and "geometry" in el:
            coords = _pts(el["geometry"])
            if len(coords) >= 2:
                feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                              "properties": {"name": name}})
        elif el["type"] == "relation":
            for line in lines_from_relation(el):
                for part in clip_parts(line):
                    feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": part},
                                  "properties": {"name": name}})


if __name__ == "__main__":
    if "pois" in sys.argv:
        fetch_pois()
    elif "transit" in sys.argv:
        fetch_transit()
    elif "waterways" in sys.argv:
        fetch_waterways()
    else:
        main()
        fetch_pois()
        fetch_transit()
        fetch_waterways()
