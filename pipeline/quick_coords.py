"""Fetch one project page per locality to get coordinates, then assign to all projects.

usage: python quick_coords.py <city>
Reads out/<city>/mb_index.json, fetches one project per locality for lat/lng,
writes out/<city>/mb_projects.json with coordinates injected.
"""
import json
import pathlib
import sys
from collections import defaultdict

import mb_crawl
import mb_parse

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "out"
CITIES = json.loads((ROOT.parent / "data" / "cities.json").read_text())
CITY = sys.argv[1] if len(sys.argv) > 1 else "gurgaon"
CFG = CITIES[CITY]


def main():
    idx = json.loads((OUT / CITY / "mb_index.json").read_text())
    print(f"Loaded {len(idx)} projects", flush=True)

    by_loc = defaultdict(list)
    for p in idx:
        by_loc[p.get("locality") or ""].append(p)
    print(f"{len(by_loc)} unique localities", flush=True)

    bbox = CFG["bbox"]
    loc_coords = {}
    fetched = 0

    for loc, projects in sorted(by_loc.items(), key=lambda x: -len(x[1])):
        if not loc:
            continue
        # try fetching first project in this locality
        for p in projects[:3]:
            html = mb_crawl.fetch(p["url"])
            fetched += 1
            if not html:
                continue
            try:
                detail = mb_parse.parse_project_page(html)
            except Exception:
                continue
            lat, lng = detail.get("lat"), detail.get("lng")
            if lat and lng and bbox[0] < lat < bbox[2] and bbox[1] < lng < bbox[3]:
                loc_coords[loc] = (lat, lng)
                # also enrich this project with full detail data
                for k, v in detail.items():
                    if v not in (None, [], ""):
                        p[k] = v
                break

        if fetched % 50 == 0:
            print(f"fetched {fetched}, located {len(loc_coords)}/{len(by_loc)} localities", flush=True)

    print(f"Done: fetched {fetched} pages, located {len(loc_coords)} localities", flush=True)

    # assign coordinates to all projects in located localities
    placed = 0
    for p in idx:
        loc = p.get("locality") or ""
        if not p.get("lat") and loc in loc_coords:
            p["lat"], p["lng"] = loc_coords[loc]
            placed += 1

    print(f"Placed {placed} additional projects by locality coordinates", flush=True)

    out_dir = OUT / CITY
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mb_projects.json").write_text(json.dumps(idx, indent=0))
    print(f"Wrote {out_dir / 'mb_projects.json'} ({len(idx)} projects)", flush=True)


if __name__ == "__main__":
    main()
