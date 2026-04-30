"""
OpenStreetMap Overpass scraper — businesses within 100 miles of White Plains, NY.
Free, no API key. Covers NYC, Long Island, all of CT, most of NJ, Hudson Valley, parts of MA.

Strategy:
1. Split 100mi radius into a grid of bounding boxes (~20mi cells)
2. For each cell, query Overpass for:
   - amenity = restaurant, bar, cafe, fast_food, pub
   - shop = * (all shops)
   - craft = * (plumber, electrician, etc.)
   - office = * (lawyer, accountant, estate_agent, etc.)
   - tourism = hotel, motel, guest_house
   - leisure = fitness_centre, sports_centre
3. Collect unique businesses with name + website
4. Website scrape → emails (parallel, resumable)

Output: targets/osm_100mi_leads.csv (incremental, resumable via cache)
"""
import os, re, json, csv, time, sys, math, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent
OVERPASS = "https://overpass-api.de/api/interpreter"

# White Plains NY center
CLAT, CLON = 41.0340, -73.7629
RADIUS_MILES = 100

# Grid cells: 0.3 deg ≈ 20 miles; covers 100mi radius with ~7x7 = 49 cells (pad a bit)
CELL_DEG = 0.3
# Bounding box for 100 miles around White Plains: rough lat/lon degrees
# 1 deg lat ≈ 69 mi → 100/69 ≈ 1.45 deg
# 1 deg lon at 41°N ≈ 52 mi → 100/52 ≈ 1.92 deg
LAT_SPAN = 100 / 69.0
LON_SPAN = 100 / 52.0

CACHE_RAW = ROOT / "state" / "osm_raw.json"
EMAIL_CACHE = ROOT / "state" / "osm_email_cache.json"
OUT_CSV = ROOT / "targets" / "osm_100mi_leads.csv"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
BLOCK = (
    "example.com", "sentry.io", "wixpress", "godaddy",
    "squarespace", "wixstatic", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".webp", "{{", "}}", "u003",
)


def cells():
    """Yield (south, west, north, east) bounding boxes covering 100mi circle."""
    # Pad bbox slightly; we'll filter to circle after
    min_lat = CLAT - LAT_SPAN
    max_lat = CLAT + LAT_SPAN
    min_lon = CLON - LON_SPAN
    max_lon = CLON + LON_SPAN
    lat = min_lat
    while lat < max_lat:
        lon = min_lon
        while lon < max_lon:
            yield (lat, lon, lat + CELL_DEG, lon + CELL_DEG)
            lon += CELL_DEG
        lat += CELL_DEG


def in_circle(lat: float, lon: float) -> bool:
    """Check if point is within RADIUS_MILES of White Plains."""
    # Haversine-ish quick check
    dlat = (lat - CLAT) * 69.0
    dlon = (lon - CLON) * 52.0
    return math.hypot(dlat, dlon) <= RADIUS_MILES


# Overpass QL: grab businesses within bbox with names
OVERPASS_QUERY = """
[out:json][timeout:90];
(
  node["amenity"~"restaurant|bar|cafe|fast_food|pub|nightclub|bakery|biergarten|food_court|ice_cream|pharmacy|veterinary|dentist|doctors|clinic|hospital"]({s},{w},{n},{e});
  node["shop"]({s},{w},{n},{e});
  node["craft"]({s},{w},{n},{e});
  node["office"]({s},{w},{n},{e});
  node["tourism"~"hotel|motel|guest_house|hostel"]({s},{w},{n},{e});
  node["leisure"~"fitness_centre|sports_centre|dance|golf_course"]({s},{w},{n},{e});
  way["amenity"~"restaurant|bar|cafe|fast_food|pub|nightclub|bakery|biergarten|food_court|ice_cream|pharmacy|veterinary|dentist|doctors|clinic|hospital"]({s},{w},{n},{e});
  way["shop"]({s},{w},{n},{e});
  way["tourism"~"hotel|motel|guest_house|hostel"]({s},{w},{n},{e});
  way["leisure"~"fitness_centre|sports_centre"]({s},{w},{n},{e});
);
out tags center;
""".strip()


def overpass_query(bbox) -> list[dict]:
    s, w, n, e = bbox
    q = OVERPASS_QUERY.format(s=s, w=w, n=n, e=e)
    data = f"data={urllib.parse.quote(q)}".encode()
    req = urllib.request.Request(
        OVERPASS,
        data=data,
        method="POST",
        headers={
            "User-Agent": "smore-labs-local-smb-lookup (claudesonnet111@gmail.com)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    for attempt in range(4):
        try:
            raw = urllib.request.urlopen(req, timeout=120).read()
            return json.loads(raw).get("elements", [])
        except urllib.error.HTTPError as he:
            if he.code == 429:
                time.sleep(15 * (attempt + 1))
                continue
            print(f"  ! HTTP {he.code}: {he.read().decode()[:120]}")
            return []
        except Exception as e:
            print(f"  ! {e} (retry)")
            time.sleep(10 * (attempt + 1))
    return []


def normalize_website(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def sweep() -> dict:
    CACHE_RAW.parent.mkdir(parents=True, exist_ok=True)
    by_key: dict = json.loads(CACHE_RAW.read_text()) if CACHE_RAW.exists() else {}
    print(f"♻️  Cache: {len(by_key)} OSM businesses already collected")

    box_list = [c for c in cells() if in_circle((c[0] + c[2]) / 2, (c[1] + c[3]) / 2)]
    print(f"→ {len(box_list)} grid cells inside 100mi circle")

    for i, bbox in enumerate(box_list, 1):
        elements = overpass_query(bbox)
        added = 0
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
            key = f"{el.get('type')}/{el.get('id')}"
            if key in by_key:
                continue
            website = tags.get("contact:website") or tags.get("website") or ""
            email = tags.get("contact:email") or tags.get("email") or ""
            phone = tags.get("contact:phone") or tags.get("phone") or ""
            category = (
                tags.get("amenity") or tags.get("shop") or tags.get("craft")
                or tags.get("office") or tags.get("tourism") or tags.get("leisure")
                or "other"
            )
            # get lat/lon (ways have center)
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if lat and lon and not in_circle(lat, lon):
                continue
            by_key[key] = {
                "osm_id": key,
                "name": name,
                "category": category,
                "website": normalize_website(website),
                "email": email.lower().strip() if email else "",
                "phone": phone,
                "lat": lat,
                "lon": lon,
                "address": " ".join(filter(None, [
                    tags.get("addr:housenumber", ""),
                    tags.get("addr:street", ""),
                    tags.get("addr:city", ""),
                    tags.get("addr:state", ""),
                    tags.get("addr:postcode", ""),
                ])).strip(),
            }
            added += 1
        print(f"  [{i:3d}/{len(box_list)}] bbox=({bbox[0]:.2f},{bbox[1]:.2f}) +{added:4d} total={len(by_key)}")
        if i % 5 == 0:
            CACHE_RAW.write_text(json.dumps(by_key))
        time.sleep(1.5)  # Be gentle to Overpass public API
    CACHE_RAW.write_text(json.dumps(by_key))
    return by_key


# ── Website email scraper (reused pattern) ───────────────────────────────────
class _Strip(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self._skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v and v.lower().startswith("mailto:"):
                    self.out.append(v[7:].split("?")[0])
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def fetch(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (smore-labs-scraper)"})
    try:
        return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def find_email(site: str) -> str:
    if not site:
        return ""
    base = site.rstrip("/")
    for url in (base, f"{base}/contact", f"{base}/contact-us", f"{base}/about"):
        html = fetch(url)
        if not html:
            continue
        strip = _Strip()
        try:
            strip.feed(html)
        except Exception:
            pass
        text = " ".join(strip.out)
        for m in EMAIL_RE.findall(text):
            low = m.lower()
            if any(b in low for b in BLOCK):
                continue
            return m
    return ""


def scrape_emails(biz: dict) -> None:
    cache = json.loads(EMAIL_CACHE.read_text()) if EMAIL_CACHE.exists() else {}
    # Skip ones OSM already had email for, and ones already cached
    todo = [b for b in biz.values()
            if b.get("website") and not b.get("email") and b["osm_id"] not in cache]
    print(f"\n→ Scraping emails from {len(todo)} websites ({len(cache)} cached)")

    def work(b):
        return b["osm_id"], find_email(b["website"])

    done, hit = 0, 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = [ex.submit(work, b) for b in todo]
        for f in as_completed(futs):
            pid, email = f.result()
            cache[pid] = email
            if pid in biz:
                biz[pid]["email"] = email
            done += 1
            if email:
                hit += 1
            if done % 100 == 0:
                EMAIL_CACHE.write_text(json.dumps(cache))
                print(f"  [{done}/{len(todo)}] found {hit}")
    EMAIL_CACHE.write_text(json.dumps(cache))


def main() -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    biz = sweep()
    print(f"\n✓ Overpass sweep: {len(biz)} unique businesses")
    scrape_emails(biz)

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "osm_id", "name", "category", "website", "email", "phone",
            "lat", "lon", "address",
        ])
        w.writeheader()
        for b in biz.values():
            w.writerow(b)

    with_email = [b for b in biz.values() if b.get("email")]
    print(f"\n{'='*60}")
    print(f"✅ OSM: {len(biz)} businesses | {len(with_email)} with email ({100*len(with_email)/max(1,len(biz)):.0f}%)")
    print(f"   Output: {OUT_CSV}")


if __name__ == "__main__":
    main()
