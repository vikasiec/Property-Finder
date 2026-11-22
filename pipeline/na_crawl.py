"""Polite, cached, resumable 99acres crawler.

usage: python na_crawl.py list <city>      # all list pages -> out/<city>/na_index.json
       python na_crawl.py projects <city>  # every project page -> out/<city>/na_projects.json
<city> is a key in data/cities.json (default gurgaon).
"""
import gzip
import hashlib
import json
import pathlib
import re
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).parent
CACHE = ROOT / "cache" / "na"
OUT = ROOT / "out"
CITIES = json.loads((ROOT.parent / "data" / "cities.json").read_text())
CITY = next((a for a in sys.argv[1:] if a in CITIES), "gurgaon")
CFG = CITIES[CITY]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
DELAY = 1.0

CITY_SLUGS = {"gurgaon": "gurgaon", "pune": "pune"}
LIST_URL = "https://www.99acres.com/new-projects-in-{}-ffid-page-{}"


def fetch(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".html.gz")
    if f.exists() and f.stat().st_size > 500:
        return gzip.decompress(f.read_bytes()).decode("utf-8", "ignore")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={**HEADERS, "User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=40).read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            html = raw.decode("utf-8", "ignore")
            tmp = tempfile.NamedTemporaryFile(dir=CACHE, delete=False, suffix=".tmp")
            tmp.write(gzip.compress(html.encode("utf-8"), 9))
            tmp.close()
            pathlib.Path(tmp.name).replace(f)
            time.sleep(DELAY)
            return html
        except Exception as e:
            print(f"  retry {attempt + 1} {url} {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    return None


def parse_list_page(html):
    """Extract project URLs from a 99acres listing page."""
    urls = []
    seen = set()
    for m in re.finditer(r'href="(/[^"]*-npxid-r\d+)"', html):
        path = m.group(1)
        if path not in seen:
            seen.add(path)
            urls.append("https://www.99acres.com" + path)
    return urls


def parse_total(html):
    """Extract total project count from listing page."""
    m = re.search(r'([\d,]+)\s*Projects?', html)
    return int(m.group(1).replace(",", "")) if m else None


def parse_project_page(html):
    """Extract project data from LD+JSON blocks on a project page."""
    result = {}
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
        try:
            d = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            continue

        t = d.get("@type")
        if t == "Product":
            result["name"] = d.get("name")
            result["description"] = (d.get("description") or "")[:600]
            result["image"] = d.get("image")
            offers = d.get("offers") or {}
            result["price_min"] = offers.get("lowPrice")
            result["price_max"] = offers.get("highPrice")
            result["listing_count"] = int(offers["offerCount"]) if offers.get("offerCount") else None
            brand = d.get("brand") or {}
            result["developer"] = brand.get("name")
            ar = d.get("aggregateRating") or {}
            result["rating"] = float(ar["ratingValue"]) if ar.get("ratingValue") else None
            result["rating_count"] = int(ar["ratingCount"]) if ar.get("ratingCount") else None
            result["review_count"] = int(ar["reviewCount"]) if ar.get("reviewCount") else None
            reviews = []
            for r in (d.get("review") or [])[:6]:
                rb = r.get("reviewBody") or ""
                if rb:
                    reviews.append({
                        "text": rb[:320],
                        "rating": r.get("reviewRating", {}).get("ratingValue"),
                        "by": (r.get("author") or {}).get("name"),
                        "date": r.get("datePublished"),
                    })
            result["reviews"] = reviews

        elif t == "Place":
            geo = d.get("geo") or {}
            result["lat"] = float(geo["latitude"]) if geo.get("latitude") else None
            result["lng"] = float(geo["longitude"]) if geo.get("longitude") else None

        elif t == "Residence":
            addr = d.get("address") or {}
            result["locality"] = addr.get("addressLocality")
            result["region"] = addr.get("addressRegion")
            result["pincode"] = addr.get("postalCode")
            result["address"] = addr.get("streetAddress")

    # Extract RERA, BHK configs, amenities from HTML
    rera = re.search(r'RERA[^:]*:\s*([A-Z0-9/]+)', html)
    if rera:
        result["rera_id"] = rera.group(1)

    # Possession status
    if "Ready To Move" in html:
        result["status"] = "Ready To Move"
    elif "Under Construction" in html:
        result["status"] = "Under Construction"

    # BHK types from page text
    bhks = re.findall(r'(\d)\s*BHK', html)
    if bhks:
        result["bhk_types"] = sorted(set(int(b) for b in bhks))

    # Amenities from the amenities section
    amen_match = re.findall(r'class="[^"]*amenity[^"]*"[^>]*>\s*([^<]+)', html, re.IGNORECASE)
    if amen_match:
        result["amenities"] = [a.strip() for a in amen_match if a.strip() and len(a.strip()) < 40][:30]

    # Extract npxid for dedup
    npx = re.search(r'npxid-r(\d+)', html)
    if npx:
        result["na_id"] = npx.group(1)

    return result


def crawl_list():
    slug = CITY_SLUGS.get(CITY, CITY)
    out_dir = OUT / CITY
    out_dir.mkdir(parents=True, exist_ok=True)

    first_html = fetch(LIST_URL.format(slug, 1))
    if not first_html:
        print("Failed to fetch first page", flush=True)
        return

    total = parse_total(first_html)
    urls_per_page = len(parse_list_page(first_html))
    pages = -(-total // max(urls_per_page, 1)) if total else 50
    print(f"Total projects: {total}, ~{urls_per_page}/page, {pages} pages", flush=True)

    all_urls = []
    seen = set()
    for n in range(1, pages + 1):
        html = fetch(LIST_URL.format(slug, n))
        if not html:
            continue
        urls = parse_list_page(html)
        for u in urls:
            if u not in seen:
                seen.add(u)
                all_urls.append(u)
        if n % 20 == 0:
            print(f"  page {n}/{pages}, {len(all_urls)} unique projects so far", flush=True)
            (out_dir / "na_index.json").write_text(json.dumps(all_urls, indent=0))
        if not urls:
            print(f"  page {n} had no projects, stopping", flush=True)
            break

    (out_dir / "na_index.json").write_text(json.dumps(all_urls, indent=0))
    print(f"Done: {len(all_urls)} project URLs from {n} pages -> na_index.json", flush=True)


def crawl_projects():
    out_dir = OUT / CITY
    index_file = out_dir / "na_index.json"
    if not index_file.exists():
        print("Run 'list' first to get the project index", flush=True)
        return
    urls = json.loads(index_file.read_text())
    projects = []
    if (out_dir / "na_projects.json").exists():
        projects = json.loads((out_dir / "na_projects.json").read_text())
    done_urls = {p["url"] for p in projects}
    todo = [u for u in urls if u not in done_urls]
    print(f"Total: {len(urls)}, already done: {len(done_urls)}, todo: {len(todo)}", flush=True)

    for i, url in enumerate(todo):
        html = fetch(url)
        if not html:
            continue
        p = parse_project_page(html)
        p["url"] = url
        projects.append(p)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(todo)} fetched, {len(projects)} total projects", flush=True)
            (out_dir / "na_projects.json").write_text(json.dumps(projects, indent=0))

    (out_dir / "na_projects.json").write_text(json.dumps(projects, indent=0))
    print(f"Done: {len(projects)} projects with details -> na_projects.json", flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"
    if mode == "list":
        crawl_list()
    elif mode == "projects":
        crawl_projects()
    else:
        print(f"Unknown mode: {mode}. Use 'list' or 'projects'")
