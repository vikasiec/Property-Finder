"""Compare two listing snapshots once a later crawl exists.

usage: python liquidity_track.py <city>

Looks for pipeline/cache/listing_snapshots/<city>/*.json. With fewer than
two snapshots it writes nothing. Each snapshot is a {society_id: sale_count} map.
"""
import json
import sys
from pathlib import Path

import scores

SNAP = scores.ROOT / "cache" / "listing_snapshots"


def track(city):
    folder = SNAP / city
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    if len(files) < 2:
        print(f"{city}: need two listing snapshots in {folder} before turnover can be scored")
        return None
    previous = json.loads(files[-2].read_text(encoding="utf-8"))
    current = json.loads(files[-1].read_text(encoding="utf-8"))
    out = {}
    for sid, prev in previous.items():
        now = current.get(sid, 0)
        base = prev or now or 1
        out[sid] = {"previous": prev, "current": now, "turnover": round(abs(prev - now) / base, 3)}
    dest = scores.OUT / city / "liquidity_tracking.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"from": files[-2].name, "to": files[-1].name, "societies": out}, indent=2), encoding="utf-8")
    print(f"turnover for {len(out)} societies -> {dest}")
    return dest


if __name__ == "__main__":
    track(sys.argv[1] if len(sys.argv) > 1 else "pune")
