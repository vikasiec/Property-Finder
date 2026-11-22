"""Fetch UDISE schools for a city and write out/<city>/udise_schools.json.

Know Your School lists schools by block, then asks for a captcha image before it
returns that list. This script replays the public block lookup. When the list is
blocked, it reads the DataMeet UDISE extract and keeps schools inside the city bbox.

usage: python udise_fetch.py <city>
"""
import csv
import io
import json
import pathlib
import re
import sqlite3
import sys
import time
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).parent
CACHE = ROOT / "cache" / "udise"
OUT = ROOT / "out"
CITIES = json.loads((ROOT.parent / "data" / "cities.json").read_text(encoding="utf-8"))

API = "https://kys.udiseplus.gov.in/web-app/api/"
HEADERS = {
    "User-Agent": "flat-finder/0.1",
    "X-APP-SIGNATURE": "9f2c7a4b8e1d6c3f5a9b0e2d4f6a7c8b",
    "Accept": "application/json",
}
DATAMEET_ZIP = "https://raw.githubusercontent.com/datameet/udise_schools/master/data/udise_schools.zip"
# state name, district name, UDISE district code
# state, list of (district name, UDISE district code) from the DataMeet extract
CITY_DISTRICT = {
    "pune": ("MAHARASHTRA", [("PUNE", "2725")]),
    "mumbai": ("MAHARASHTRA", [("MUMBAI II", "2723"), ("MUMBAI (SUBURBAN)", "2722")]),
    "bangalore": ("KARNATAKA", [("BENGALURU U SOUTH", "2920"), ("BENGALURU U NORTH", "2928"), ("BENGALURU RURAL", "2921")]),
    "hyderabad": ("TELANGANA", [("HYDERABAD", "3622"), ("MEDCHAL", "3621"), ("RANGAREDDY", "3623")]),
}
BOARDS = ("CBSE", "ICSE", "ISC", "IGCSE", "IB")


def in_bbox(lat, lng, bbox):
    south, west, north, east = bbox
    return south <= lat <= north and west <= lng <= east


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def coords_of(row):
    """Prefer the accurate lat/lon pair. Skip a pair that is missing or zero."""
    for lat_key, lng_key in (("lat", "lon"), ("lat", "lng"), ("latitude", "longitude")):
        lat, lng = _num(row.get(lat_key)), _num(row.get(lng_key))
        if lat and lng:
            return round(lat, 5), round(lng, 5)
    return None, None


def board_of(*values):
    for value in values:
        text = (value or "").upper()
        for board in BOARDS:
            if re.search(rf"\b{board}\b", text):
                return board
        if re.search(r"\bSTATE\b", text):
            return "State"
    return ""


def address_of(*parts):
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


def school_record(row, source):
    """Map one KYS or DataMeet row onto the pipeline school shape."""
    lat, lng = coords_of(row)
    if lat is None:
        return None
    if source == "kys":
        name = row.get("schoolName") or row.get("name")
        code = row.get("udiseschCode") or row.get("udiseSchCode") or row.get("udiseCode") or ""
        board = board_of(row.get("board"), row.get("schBoard"), row.get("schoolType"))
        management = row.get("managementName") or row.get("management") or ""
        category = row.get("schCategoryType") or row.get("category") or row.get("schoolCategory") or ""
        address = address_of(row.get("address"), row.get("villageName") or row.get("lgdvillName"), row.get("blockName"), row.get("districtName"))
    else:
        name = row.get("schname") or row.get("school_name") or row.get("name")
        code = row.get("schcd") or row.get("udise_code") or ""
        board = board_of(row.get("school_typ"), row.get("schtype"), row.get("board"))
        management = row.get("management") or ""
        category = row.get("school_cat") or row.get("schcat") or ""
        address = address_of(row.get("vilname"), row.get("dtname"), row.get("pincode"))
    name = (name or "").strip()
    if not name:
        return None
    return {
        "name": name,
        "lat": lat,
        "lng": lng,
        "board": board,
        "management": str(management or "").strip(),
        "category": str(category or "").strip(),
        "udise_code": str(code or "").strip(),
        "address": address,
    }


def district_row(row, code, name, state_name="MAHARASHTRA"):
    raw = row.get("udise_dtco") or row.get("udiseDistrictCode") or ""
    text = str(raw).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if text == code:
        return True
    dtname = str(row.get("dtname") or row.get("districtName") or "").strip().upper()
    state = str(row.get("stname") or row.get("stateName") or "").strip().upper()
    return dtname == name and (not state or state_name.upper() in state)


def block_code(row):
    code = str(row.get("schcd") or row.get("udiseschCode") or row.get("udise_code") or "")
    digits = re.sub(r"\D", "", code)
    if len(digits) >= 6:
        return digits[4:6]
    return "unknown"


def schools_in_bbox(rows, bbox, source, code, name):
    out = []
    seen = set()
    for row in rows:
        if source != "kys" and not district_row(row, code, name):
            continue
        school = school_record(row, source)
        if not school or not in_bbox(school["lat"], school["lng"], bbox):
            continue
        key = school["udise_code"] or (school["name"], school["lat"], school["lng"])
        if key in seen:
            continue
        seen.add(key)
        out.append(school)
    return out


def get_json(url, tries=3, delay=0.5):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            time.sleep(delay)
            return payload
        except Exception as exc:
            last = exc
            time.sleep(delay)
            print(f"retry {attempt + 1}/{tries} {url} {exc}", flush=True)
    raise last


def captcha_blocked(payload):
    if not isinstance(payload, dict) or payload.get("status") is True:
        return False
    return "captcha" in json.dumps(payload).lower()


def kys_rows(payload):
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict) and isinstance(data.get("content"), list):
        return data["content"]
    if isinstance(data, list):
        return data
    return []


def pick_year(years):
    ranked = [y for y in years if int(y.get("yearId") or 0) > 0]
    if not ranked:
        return years[0]
    return max(ranked, key=lambda y: int(y.get("yearId") or 0))


def find_named(rows, key, expected):
    expected = expected.upper()
    for row in rows:
        if str(row.get(key) or "").strip().upper() == expected:
            return row
    return None


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "block"


def fetch_kys_blocks(cache, state_name, district_name):
    years = get_json(f"{API}master/year?year=1")
    year_rows = years.get("data") if isinstance(years, dict) else years
    year = pick_year(year_rows or [])
    year_id = year["yearId"]
    states = get_json(f"{API}states?yearId={year_id}")
    state = find_named(states.get("data") or [], "stateName", state_name)
    if not state:
        raise RuntimeError(f"UDISE state not found: {state_name}")
    districts = get_json(f"{API}districts?stateId={state['stateId']}&yearId={year_id}")
    district = find_named(districts.get("data") or [], "districtName", district_name)
    if not district:
        raise RuntimeError(f"UDISE district not found: {district_name}")
    blocks = get_json(f"{API}blocks?districtId={district['districtId']}&yearId={year_id}")
    block_rows = blocks.get("data") or []
    (cache / "blocks.json").write_text(json.dumps(blocks), encoding="utf-8")
    print(f"UDISE blocks {len(block_rows)} year {year.get('yearDesc') or year_id}", flush=True)
    return state, district, block_rows


def fetch_kys_schools(cache, state, district, blocks):
    """Return school rows, or None when the list endpoint requires a captcha."""
    rows = []
    for block in blocks:
        block_id = block.get("blockId")
        query = (
            f"stateId={state['stateId']}&districtId={district['districtId']}"
            f"&blockId={block_id}&villageId=&clusterId=&categoryId=&managementId="
        )
        url = f"{API}search-school/by-region?{query}&captcha="
        payload = get_json(url)
        name = slug(block.get("blockName") or block.get("eduBlockName"))
        (cache / f"{block_id}-{name}.json").write_text(json.dumps(payload), encoding="utf-8")
        if captcha_blocked(payload):
            print("UDISE list requires a captcha; using the DataMeet extract", flush=True)
            return None
        got = kys_rows(payload)
        print(f"block {block.get('blockName')} {len(got)}", flush=True)
        rows.extend(got)
    return rows


def download(url, dest, tries=3):
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "flat-finder/0.1"})
            with urllib.request.urlopen(req, timeout=180) as resp, dest.open("wb") as out:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
            return dest
        except Exception as exc:
            last = exc
            print(f"retry {attempt + 1}/{tries} {url} {exc}", flush=True)
            time.sleep(0.5)
    raise last


def _row_from_feature(feature):
    props = dict(feature.get("properties") or {})
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or [None, None]
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        props.setdefault("lon", coords[0])
        props.setdefault("lat", coords[1])
    return props


def iter_datameet(path, code, name):
    with zipfile.ZipFile(path) as zipped:
        names = [n for n in zipped.namelist() if not n.endswith("/")]
        print("datameet zip", ", ".join(names[:8]), flush=True)
        sqlite_name = next((n for n in names if n.endswith((".sqlite", ".db", ".sqlite3"))), None)
        if sqlite_name:
            raw = zipped.read(sqlite_name)
            db_path = path.with_suffix(".sqlite")
            if not db_path.exists() or db_path.stat().st_size != len(raw):
                db_path.write_bytes(raw)
            conn = sqlite3.connect(db_path)
            try:
                tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                table = "udise_schools" if "udise_schools" in tables else tables[0]
                cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
                where = []
                params = []
                if "udise_dtco" in cols:
                    where.append("CAST(udise_dtco AS TEXT) IN (?, ?)")
                    params.extend([code, f"{code}.0"])
                if "dtname" in cols:
                    where.append("UPPER(dtname) = ?")
                    params.append(name)
                sql = f'SELECT * FROM "{table}"'
                if where:
                    sql += " WHERE " + " OR ".join(where)
                cur = conn.execute(sql, params)
                cols = [d[0] for d in cur.description]
                for rec in cur:
                    yield dict(zip(cols, rec))
            finally:
                conn.close()
            return
        csv_name = next((n for n in names if n.endswith(".csv")), None)
        if csv_name:
            with zipped.open(csv_name) as handle:
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace", newline="")
                yield from csv.DictReader(text)
            return
        geo_name = next((n for n in names if n.endswith((".geojson", ".json"))), None)
        if geo_name:
            payload = json.loads(zipped.read(geo_name))
            features = payload.get("features") if isinstance(payload, dict) else payload
            for feature in features:
                yield _row_from_feature(feature)
            return
    raise RuntimeError(f"no school table in {path}")


def cache_blocks(cache, rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(block_code(row), []).append(row)
    for code, group in grouped.items():
        (cache / f"block-{code}.json").write_text(json.dumps(group), encoding="utf-8")


def fetch(city):
    if city not in CITIES:
        raise SystemExit(f"unknown city {city}")
    if city not in CITY_DISTRICT:
        raise SystemExit(f"no UDISE district mapping for {city}")
    state_name, districts = CITY_DISTRICT[city]
    bbox = CITIES[city]["bbox"]
    cache = CACHE / city
    cache.mkdir(parents=True, exist_ok=True)
    state, district, blocks = fetch_kys_blocks(cache, state_name, districts[0][0])
    rows = fetch_kys_schools(cache, state, district, blocks)
    source = "kys"
    if rows is None:
        zip_path = download(DATAMEET_ZIP, cache / "udise_schools.zip")
        rows = []
        for district_name, code in districts:
            rows.extend(row for row in iter_datameet(zip_path, code, district_name)
                        if district_row(row, code, district_name, state_name))
        cache_blocks(cache, rows)
        source = "datameet"
        print(f"datameet {[name for name, _ in districts]} rows {len(rows)}", flush=True)
    schools = []
    seen = set()
    for district_name, code in districts:
        for school in schools_in_bbox(rows, bbox, source, code, district_name):
            if school["udise_code"] in seen:
                continue
            seen.add(school["udise_code"])
            schools.append(school)
    out = OUT / city
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "udise_schools.json"
    dest.write_text(json.dumps(schools), encoding="utf-8")
    print(f"udise schools {len(schools)} -> {dest}", flush=True)
    return schools


if __name__ == "__main__":
    city = next((a for a in sys.argv[1:] if a in CITIES), None)
    if not city:
        raise SystemExit("usage: python udise_fetch.py <city>")
    fetch(city)
