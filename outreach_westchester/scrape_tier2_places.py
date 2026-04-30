"""
Phase 2 scraper: Google Places (New) for 31 anchors within 100mi of White Plains
but OUTSIDE Westchester (Westchester already covered by scrape_leads.py).

Adds: NYC 5 boroughs, Long Island, CT (Stamford→Hartford corridor),
      Hudson Valley (Nyack→Kingston), northern NJ (Newark→Hackensack).

Budget: ~31 anchors × 30 categories × $0.032 ≈ $30.

Output merges into the existing westchester_leads.csv via a dedupe pass at the end.
"""
import os, re, json, csv, time, sys, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT.parent / ".env"

def load_key() -> str:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE}")
    text = ENV_FILE.read_text()
    m = re.search(r"^GOOGLE_PLACES_API_KEY\s*=\s*(.+)$", text, re.M) \
        or re.search(r"^GOOGLE_API_KEY\s*=\s*(.+)$", text, re.M)
    if not m:
        sys.exit("GOOGLE_PLACES_API_KEY not in .env")
    return m.group(1).strip().strip('"').strip("'")

API_KEY = load_key()

ANCHORS = [
    # NYC boroughs
    ("Manhattan",       40.7831, -73.9712),
    ("Brooklyn",        40.6782, -73.9442),
    ("Queens",          40.7282, -73.7949),
    ("Bronx",           40.8448, -73.8648),
    ("Staten Island",   40.5795, -74.1502),
    # Long Island
    ("Hempstead",       40.7062, -73.6187),
    ("Garden City",     40.7268, -73.6343),
    ("Huntington",      40.8682, -73.4254),
    ("Smithtown",       40.8560, -73.2007),
    ("Brookhaven",      40.7795, -72.9151),
    # CT
    ("Greenwich",       41.0262, -73.6282),
    ("Stamford",        41.0534, -73.5387),
    ("Norwalk",         41.1177, -73.4082),
    ("Bridgeport",      41.1865, -73.1952),
    ("New Haven",       41.3083, -72.9279),
    ("Danbury",         41.3948, -73.4540),
    ("Waterbury",       41.5581, -73.0515),
    ("Hartford",        41.7658, -72.6734),
    # Hudson Valley
    ("Nyack",           41.0909, -73.9179),
    ("Suffern",         41.1148, -74.1496),
    ("Poughkeepsie",    41.7004, -73.9209),
    ("Newburgh",        41.5034, -74.0104),
    ("Middletown NY",   41.4459, -74.4229),
    ("Kingston NY",     41.9270, -73.9974),
    # Northern NJ
    ("Newark",          40.7357, -74.1724),
    ("Jersey City",     40.7178, -74.0431),
    ("Paterson",        40.9168, -74.1718),
    ("Clifton",         40.8584, -74.1638),
    ("Elizabeth",       40.6640, -74.2107),
    ("Edison",          40.5187, -74.4121),
    ("Morristown",      40.7968, -74.4815),
    ("Hackensack",      40.8859, -74.0435),
    ("Englewood",       40.8929, -73.9726),
    ("Ridgewood NJ",    40.9790, -74.1165),
    ("Montclair",       40.8259, -74.2090),
]

RADIUS_M = 5000  # 3.1 mi per anchor — overlap OK, dedup handles

CATEGORIES = [
    ("restaurant",   "restaurants"),
    ("bar",          "bars"),
    ("cafe",         "coffee shops"),
    ("pizzeria",     "pizzerias"),
    ("diner",        "diners"),
    ("bakery",       "bakeries"),
    ("caterer",      "caterers"),
    ("winery",       "wineries"),
    ("brewery",      "breweries"),
    ("plumber",      "plumbers"),
    ("electrician",  "electricians"),
    ("hvac",         "HVAC contractors"),
    ("contractor",   "general contractors"),
    ("roofer",       "roofing contractors"),
    ("landscaper",   "landscapers"),
    ("painter",      "painting contractors"),
    ("flooring",     "flooring contractors"),
    ("locksmith",    "locksmiths"),
    ("pest_control", "pest control"),
    ("appliance_repair","appliance repair"),
    ("salon",        "hair salons"),
    ("barber",       "barber shops"),
    ("dentist",      "dentists"),
    ("veterinarian", "veterinarians"),
    ("dry_cleaner",  "dry cleaners"),
    ("auto_repair",  "auto repair shops"),
    ("gym",          "gyms"),
    ("yoga",         "yoga studios"),
    ("chiropractor", "chiropractors"),
    ("cleaning",     "cleaning services"),
]

OUT_CSV = ROOT / "targets" / "tier2_leads.csv"
PLACES_CACHE = ROOT / "state" / "tier2_places_raw.json"
EMAIL_CACHE = ROOT / "state" / "tier2_email_cache.json"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
BLOCK = (
    "example.com", "yourdomain", "sentry.io", "wixpress.com", "godaddy",
    "squarespace", "wixstatic", ".png", ".jpg", ".jpeg", ".gif", ".svg",
)


def places_search(query: str, lat: float, lng: float) -> dict:
    body = {
        "textQuery": query,
        "locationBias": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": RADIUS_M}
        },
    }
    req = urllib.request.Request(
        "https://places.googleapis.com/v1/places:searchText",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,"
                "places.websiteUri,places.nationalPhoneNumber,places.primaryType"
            ),
        },
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
    except urllib.error.HTTPError as e:
        print(f"  ! HTTP {e.code}: {e.read().decode()[:120]}")
        return {}
    except Exception as e:
        print(f"  ! {e}")
        return {}


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


def sweep() -> dict:
    PLACES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    by_id = json.loads(PLACES_CACHE.read_text()) if PLACES_CACHE.exists() else {}
    print(f"♻️  Tier2 places cache: {len(by_id)} already")

    total = len(ANCHORS) * len(CATEGORIES)
    done = 0
    start = time.time()
    for town, lat, lng in ANCHORS:
        for slug, label in CATEGORIES:
            done += 1
            query = f"{label} in {town}"
            resp = places_search(query, lat, lng)
            added = 0
            for p in resp.get("places", []):
                pid = p.get("id")
                if not pid or pid in by_id:
                    continue
                by_id[pid] = {
                    "place_id": pid,
                    "name": p.get("displayName", {}).get("text", ""),
                    "category": slug,
                    "primary_type": p.get("primaryType", ""),
                    "website": p.get("websiteUri", ""),
                    "phone": p.get("nationalPhoneNumber", ""),
                    "address": p.get("formattedAddress", ""),
                    "town": town,
                    "email": "",
                }
                added += 1
            if done % 30 == 0:
                elapsed = time.time() - start
                eta = (total - done) * (elapsed / done) if done else 0
                print(f"  [{done}/{total}] +{added:2d} {town:16s} {label:18s} total={len(by_id)} ETA {eta:.0f}s")
                PLACES_CACHE.write_text(json.dumps(by_id))
    PLACES_CACHE.write_text(json.dumps(by_id))
    return by_id


def scrape_emails(places: dict) -> None:
    cache = json.loads(EMAIL_CACHE.read_text()) if EMAIL_CACHE.exists() else {}
    todo = [p for p in places.values() if p.get("website") and p["place_id"] not in cache]
    print(f"\n→ Scraping emails from {len(todo)} sites ({len(cache)} cached)")

    def work(p):
        return p["place_id"], find_email(p["website"])

    done, hit = 0, 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = [ex.submit(work, p) for p in todo]
        for f in as_completed(futs):
            pid, em = f.result()
            cache[pid] = em
            places[pid]["email"] = em
            done += 1
            if em:
                hit += 1
            if done % 100 == 0:
                EMAIL_CACHE.write_text(json.dumps(cache))
                print(f"  [{done}/{len(todo)}] hits={hit}")
    EMAIL_CACHE.write_text(json.dumps(cache))


def main():
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    places = sweep()
    print(f"\n✓ Tier2 sweep: {len(places)} unique places")
    scrape_emails(places)

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "place_id", "name", "category", "primary_type",
            "website", "phone", "address", "town", "email",
        ])
        w.writeheader()
        for p in places.values():
            w.writerow(p)

    with_email = [p for p in places.values() if p.get("email")]
    print(f"\n{'='*60}")
    print(f"✅ Tier2: {len(places)} businesses | {len(with_email)} with email")
    print(f"   Output: {OUT_CSV}")


if __name__ == "__main__":
    main()
