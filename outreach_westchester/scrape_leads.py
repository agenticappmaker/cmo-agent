"""
Westchester County lead scraper — full coverage.
- Grid: 25 town anchors covering all of Westchester County NY.
- Categories: 30 verticals (hospitality, trades, professional services, retail).
- Places API (New) Text Search with locationBias circle per anchor.
- Deduplicates by place_id.
- Parallel website contact-page scraping for public emails.
- Outputs: targets/westchester_leads.csv

Budget: ~750 API calls × $0.032 ≈ $24 worst case (field mask kept tight).
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

# ── Town anchors (25 points covering Westchester County) ─────────────────────
ANCHORS = [
    ("White Plains",        41.0340, -73.7629),
    ("Yonkers",             40.9312, -73.8987),
    ("New Rochelle",        40.9115, -73.7824),
    ("Mount Vernon",        40.9126, -73.8371),
    ("Scarsdale",           40.9893, -73.7879),
    ("Rye",                 40.9854, -73.6835),
    ("Harrison",            40.9693, -73.7127),
    ("Mamaroneck",          40.9481, -73.7326),
    ("Tarrytown",           41.0762, -73.8587),
    ("Sleepy Hollow",       41.0857, -73.8590),
    ("Ossining",            41.1626, -73.8615),
    ("Peekskill",           41.2895, -73.9204),
    ("Mount Kisco",         41.2045, -73.7290),
    ("Chappaqua",           41.1579, -73.7663),
    ("Pleasantville",       41.1348, -73.7857),
    ("Bedford",             41.2045, -73.6407),
    ("Armonk",              41.1268, -73.7140),
    ("Hastings-on-Hudson",  40.9926, -73.8790),
    ("Dobbs Ferry",         41.0134, -73.8687),
    ("Irvington",           41.0412, -73.8679),
    ("Elmsford",            41.0554, -73.8187),
    ("Eastchester",         40.9548, -73.8157),
    ("Bronxville",          40.9398, -73.8337),
    ("Port Chester",        41.0009, -73.6640),
    ("Yorktown Heights",    41.2710, -73.7735),
]
RADIUS_M = 4500  # ~2.8mi — tight enough to return distinct sets per town

# ── Categories (30 verticals) ────────────────────────────────────────────────
CATEGORIES = [
    # Hospitality (9)
    ("restaurant",   "restaurants"),
    ("bar",          "bars"),
    ("cafe",         "coffee shops"),
    ("pizzeria",     "pizzerias"),
    ("diner",        "diners"),
    ("bakery",       "bakeries"),
    ("caterer",      "caterers"),
    ("winery",       "wineries"),
    ("brewery",      "breweries"),
    # Trades (11)
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
    # Professional services + retail (10)
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

OUT_CSV = ROOT / "targets" / "westchester_leads.csv"
PLACES_CACHE = ROOT / "state" / "places_raw.json"
EMAIL_CACHE = ROOT / "state" / "email_cache.json"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
BLOCK = (
    "example.com", "yourdomain", "sentry.io", "wixpress.com", "godaddy",
    "squarespace", "sentry-next", "wixstatic",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
)


def places_search(query: str, lat: float, lng: float, page_token: str | None = None) -> dict:
    body: dict = {
        "textQuery": query,
        "locationBias": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": RADIUS_M}
        },
    }
    if page_token:
        body["pageToken"] = page_token
    req = urllib.request.Request(
        "https://places.googleapis.com/v1/places:searchText",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,"
                "places.websiteUri,places.nationalPhoneNumber,places.primaryType,"
                "nextPageToken"
            ),
        },
    )
    try:
        r = urllib.request.urlopen(req, timeout=20).read().decode()
        return json.loads(r)
    except urllib.error.HTTPError as e:
        print(f"  ! HTTP {e.code}: {e.read().decode()[:160]}")
        return {}
    except Exception as e:
        print(f"  ! {e}")
        return {}


# ── HTML → email extractor ───────────────────────────────────────────────────
class _TextStripper(HTMLParser):
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


def fetch_text(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (local-smb-outreach-scraper)"}
    )
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read()
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def find_email(home_url: str) -> str:
    if not home_url:
        return ""
    base = home_url.rstrip("/")
    for url in (base, f"{base}/contact", f"{base}/contact-us", f"{base}/about"):
        html = fetch_text(url)
        if not html:
            continue
        strip = _TextStripper()
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


# ── Phase 1: Places API sweep ────────────────────────────────────────────────
def sweep_places() -> dict[str, dict]:
    PLACES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    by_id: dict[str, dict] = {}
    if PLACES_CACHE.exists():
        by_id = json.loads(PLACES_CACHE.read_text())
        print(f"♻️  Resuming from cache: {len(by_id)} places already fetched")

    total_queries = len(ANCHORS) * len(CATEGORIES)
    done = 0
    start = time.time()
    for town, lat, lng in ANCHORS:
        for slug, label in CATEGORIES:
            done += 1
            query = f"{label} in {town} NY"
            # One page per query is plenty (up to 20 results) — more pages = more $$
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
            if done % 25 == 0:
                elapsed = time.time() - start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total_queries - done) / rate if rate > 0 else 0
                print(f"  [{done}/{total_queries}] +{added:2d} {town:18s} {label:20s} | total={len(by_id)} ETA {eta:.0f}s")
                PLACES_CACHE.write_text(json.dumps(by_id))
    PLACES_CACHE.write_text(json.dumps(by_id))
    return by_id


# ── Phase 2: website email scrape (parallel) ─────────────────────────────────
def scrape_emails(places: dict[str, dict]) -> None:
    cache: dict[str, str] = json.loads(EMAIL_CACHE.read_text()) if EMAIL_CACHE.exists() else {}
    todo = [p for p in places.values() if p.get("website") and p["place_id"] not in cache]
    print(f"\n→ Scraping emails from {len(todo)} websites ({len(cache)} already cached)")

    def work(place):
        email = find_email(place["website"])
        return place["place_id"], email

    done = 0
    hit = 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = [ex.submit(work, p) for p in todo]
        for f in as_completed(futs):
            pid, email = f.result()
            cache[pid] = email
            places[pid]["email"] = email
            done += 1
            if email:
                hit += 1
            if done % 50 == 0:
                EMAIL_CACHE.write_text(json.dumps(cache))
                print(f"  scanned {done}/{len(todo)} | emails found so far: {hit}")
    EMAIL_CACHE.write_text(json.dumps(cache))

    # Merge cached emails back into places (for previously scraped ones)
    for pid, email in cache.items():
        if pid in places:
            places[pid]["email"] = email


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    places = sweep_places()
    print(f"\n✓ Places sweep: {len(places)} unique businesses")

    scrape_emails(places)

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["place_id", "name", "category", "primary_type",
                        "website", "phone", "address", "town", "email"],
        )
        w.writeheader()
        for p in places.values():
            w.writerow(p)

    with_email = [p for p in places.values() if p.get("email")]
    print(f"\n{'='*60}")
    print(f"✅ Wrote {OUT_CSV}")
    print(f"   Total businesses: {len(places)}")
    print(f"   With email:       {len(with_email)} ({100*len(with_email)/max(1,len(places)):.0f}%)")
    by_cat: dict[str, int] = {}
    by_town: dict[str, int] = {}
    for p in with_email:
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
        by_town[p["town"]]   = by_town.get(p["town"], 0) + 1
    print("\n   Top categories:")
    for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])[:10]:
        print(f"     {k:18s} {v}")
    print("\n   Top towns:")
    for k, v in sorted(by_town.items(), key=lambda kv: -kv[1])[:10]:
        print(f"     {k:18s} {v}")


if __name__ == "__main__":
    main()
