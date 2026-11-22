"""Load ward crime data when a curated file exists.

usage: python safety_fetch.py <city>

Does not estimate crime. data/safety/<city>_wards.json is optional and must
be compiled from a published police or NCRB table. Without it, societies
keep no safety_score.
"""
import json
import sys

import geo
import scores

DATA = scores.ROOT.parent / "data" / "safety"


def load_wards(city):
    path = DATA / f"{city}_wards.json"
    if not path.exists():
        print(f"no curated ward file at {path}; safety scores left unset")
        return None
    wards = json.loads(path.read_text(encoding="utf-8"))
    rates = []
    for ward in wards:
        pop = ward.get("population") or 0
        weighted = (ward.get("theft") or 0) * 2 + (ward.get("burglary") or 0) * 2 + (ward.get("violent") or 0) * 3
        other = max(0, (ward.get("ipc_total") or 0) - (ward.get("theft") or 0) - (ward.get("burglary") or 0) - (ward.get("violent") or 0))
        per_lakh = ((weighted + other) / pop * 100000) if pop else None
        ward["crimes_per_lakh"] = round(per_lakh, 1) if per_lakh is not None else None
        rates.append(per_lakh)
    known = [r for r in rates if r is not None]
    lo, hi = (min(known), max(known)) if known else (0, 1)
    span = hi - lo or 1
    stations = []
    for ward in wards:
        rate = ward.get("crimes_per_lakh")
        score = None if rate is None else round(100 - (rate - lo) / span * 100)
        stations.append({
            "name": ward.get("station") or ward.get("ward"),
            "lat": ward.get("lat"),
            "lng": ward.get("lng"),
            "score": score,
            "crimes_per_lakh": rate,
        })
    return {"stations": [s for s in stations if s["lat"] is not None and s["score"] is not None],
            "source": "curated ward file", "note": "Ward-level reported crime, not personal safety."}


def assign(societies, safety):
    stations = safety["stations"]
    for society in societies:
        nearest, best = None, float("inf")
        for station in stations:
            dist = geo.dist_m((society["lng"], society["lat"]), (station["lng"], station["lat"]))
            if dist < best:
                nearest, best = station, dist
        if nearest:
            society["safety_score"] = nearest["score"]
            society["safety_zone"] = nearest["name"]


def main(city):
    safety = load_wards(city)
    if not safety:
        return
    path = scores.WEB / f"{city}.json"
    if not path.exists():
        print(f"no published city file {path}")
        return
    doc = json.loads(path.read_text(encoding="utf-8"))
    assign(doc["societies"], safety)
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"safety scores on {sum(1 for s in doc['societies'] if s.get('safety_score') is not None)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pune")
