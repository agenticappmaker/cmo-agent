"""
Yelp Fusion API scraper — businesses within 100 miles of White Plains.
Free tier: 5,000 requests/day.

Strategy:
- Yelp lets us query by location + category, max 50 results/page, up to 1,000 results/query
- Anchors: same 60 towns used across Places scrapers (Westchester + Tier2)
- Categories: Yelp alias list (restaurants, plumbing, electricians, etc.)
- Yelp does NOT return email — only website + phone. We website-scrape for emails.

Requires: YELP_API_KEY in ~/cmo-agent/.env (free from https://fusion.yelp.com/)

Output: targets/yelp_leads.csv
"""
import os, re, json, csv, time, sys, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT.parent / ".env"

def load_key() -> str:
    text = ENV_FILE.read_text()
    m = re.search(r"^YELP_API_KEY\s*=\s*(.+)$", text, re.M)
    if not m:
        print("⚠ YELP_API_KEY not in .env. Skipping Yelp sweep.")
        print("  Get a free key at https://fusion.yelp.com/ (no credit card needed)")
        print("  Then: echo 'YELP_API_KEY=<key>' >> ~/cmo-agent/.env")
        sys.exit(0)
    return m.group(1).strip().strip('"').strip("'")

API_KEY = load_key()

# Same anchor set as Phase 1 + Tier2 combined
ANCHORS = [
    # Westchester 25
    ("White Plains",        41.0340, -73.7629),
    ("Yonkers",             40.9312, -73.8987),
    ("New Rochelle",        40.9115, -73.7824),
    ("Mount Vernon",        40.9126, -73.8371),
    ("Scarsdale",           40.9893, -73.7879),
    ("Rye",                 40.9854, -73.6835),
    ("Harrison NY",         40.9693, -73.7127),
    ("Mamaroneck",          40.9481, -73.7326),
    ("Tarrytown",           41.0762, -73.8587),
    ("Sleepy Hollow",       41.0857, -73.8590),
    ("Ossining",            41.1626, -73.8615),
    ("Peekskill",           41.2895, -73.9204),
    ("Mount Kisco",         41.2045, -73.7290),
    ("Chappaqua",           41.1579, -73.7663),
    ("Pleasantville",       41.1348, -73.7857),
    ("Bedford NY",          41.2045, -73.6407),
    ("Armonk",              41.1268, -73.7140),
    ("Hastings-on-Hudson",  40.9926, -73.8790),
    ("Dobbs Ferry",         41.0134, -73.8687),
    ("Irvington",           41.0412, -73.8679),
    ("Elmsford",            41.0554, -73.8187),
    ("Eastchester",         40.9548, -73.8157),
    ("Bronxville",          40.9398, -73.8337),
    ("Port Chester",        41.0009, -73.6640),
    ("Yorktown Heights",    41.2710, -73.7735),
    # Tier2 35
    ("Manhattan",       40.7831, -73.9712),
    ("Brooklyn",        40.6782, -73.9442),
    ("Queens",          40.7282, -73.7949),
    ("Bronx",           40.8448, -73.8648),
    ("Staten Island",   40.5795, -74.1502),
    ("Hempstead",       40.7062, -73.6187),
    ("Garden City",     40.7268, -73.6343),
    ("Huntington",      40.8682, -73.4254),
    ("Smithtown",       40.8560, -73.2007),
    ("Brookhaven",      40.7795, -72.9151),
    ("Greenwich",       41.0262, -73.6282),
    ("Stamford",        41.0534, -73.5387),
    ("Norwalk",         41.1177, -73.4082),
    ("Bridgeport",      41.1865, -73.1952),
    ("New Haven",       41.3083, -72.9279),
    ("Danbury",         41.3948, -73.4540),
    ("Waterbury",       41.5581, -73.0515),
    ("Hartford",        41.7658, -72.6734),
    ("Nyack",           41.0909, -73.9179),
    ("Suffern",         41.1148, -74.1496),
    ("Poughkeepsie",    41.7004, -73.9209),
    ("Newburgh",        41.5034, -74.0104),
    ("Middletown NY",   41.4459, -74.4229),
    ("Kingston NY",     41.9270, -73.9974),
    ("Newark",          40.7357, -74.1724),
    ("Jersey City",     40.7178, -74.0431),
    ("Paterson",        40.9168, -74.1718),
    ("Clifton",         40.8584, -74.1638),
    ("Elizabeth",       40.6640, -74.2107),
    ("Edison",          40.5187, -74.4121),
    ("Morristown",      40.7968, -74.4815),
    ("Hackensack",      40.8859, -74.0435),
    ("Englewood NJ",    40.8929, -73.9726),
    ("Ridgewood NJ",    40.9790, -74.1165),
    ("Montclair",       40.8259, -74.2090),
]

# Yelp category aliases (~25)
CATEGORIES = [
    "restaurants", "bars", "cafes", "pizza", "bakeries",
    "plumbing", "electricians", "hvac", "contractors", "roofing", "landscaping",
    "painters", "flooring", "locksmiths", "pestcontrol", "appliances",
    "hair", "barbers", "dentists", "veterinarians", "drycleaning",
    "autorepair", "gyms", "yoga", "chiropractors",
]

OUT_CSV = ROOT / "targets" / "yelp_leads.csv"
RAW_CACHE = ROOT / "state" / "yelp_raw.json"
EMAIL_CACHE = ROOT / "state" / "yelp_email_cache.json"
DAILY_LIMIT = 4800  # keep below 5000 to be safe
STATE_FILE = ROOT / "state" / "yelp_usage.json"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
BLOCK = (
    "example.com", "sentry.io", "wixpress", "godaddy", "squarespace",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", "wixstatic",
)


def yelp_search(location_lat: float, location_lon: float, category: str, offset: int = 0) -> dict:
    params = {
        "latitude": location_lat,
        "longitude": location_lon,
        "categories": category,
        "limit": 50,
        "offset": offset,
        "radius": 8000,  # 8 km ≈ 5 mi per anchor — overlap with neighbors is fine
    }
    url = "https://api.yelp.com/v3/businesses/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {API_KEY}"})
    for attempt in range(3):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=15).read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"   [429 rate limit, sleeping 20s]")
                time.sleep(20)
                continue
            print(f"   ! HTTP {e.code}: {e.read().decode()[:120]}")
            return {}
        except Exception as e:
            print(f"   ! {e}")
            time.sleep(3)
    return {}


def get_usage() -> int:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text()).get("today", 0)
    return 0


def bump_usage(n: int) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    current = get_usage()
    STATE_FILE.write_text(json.dumps({"today": current + n}))


def sweep() -> dict:
    RAW_CACHE.parent.mkdir(parents=True, exist_ok=True)
    by_id = json.loads(RAW_CACHE.read_text()) if RAW_CACHE.exists() else {}
    print(f"♻️  Yelp cache: {len(by_id)} businesses")

    total = len(ANCHORS) * len(CATEGORIES)
    done = 0
    usage = get_usage()
    for town, lat, lng in ANCHORS:
        for cat in CATEGORIES:
            done += 1
            if usage >= DAILY_LIMIT:
                print(f"⏸ Yelp daily budget hit ({usage}). Saving + stopping.")
                RAW_CACHE.write_text(json.dumps(by_id))
                return by_id
            # First page
            resp = yelp_search(lat, lng, cat, offset=0)
            usage += 1
            bizs = resp.get("businesses", []) or []
            added = 0
            for b in bizs:
                bid = b.get("id")
                if not bid or bid in by_id:
                    continue
                by_id[bid] = {
                    "yelp_id": bid,
                    "name": b.get("name", ""),
                    "category": cat,
                    "website": "",  # Yelp Fusion free tier doesn't return website; we use yelp_url as proxy
                    "yelp_url": b.get("url", ""),
                    "phone": b.get("display_phone", ""),
                    "address": ", ".join(b.get("location", {}).get("display_address", [])),
                    "town": town,
                    "email": "",
                }
                added += 1
            # Extra page if more results available
            total_found = resp.get("total", 0)
            if total_found > 50 and usage < DAILY_LIMIT:
                resp2 = yelp_search(lat, lng, cat, offset=50)
                usage += 1
                for b in (resp2.get("businesses", []) or []):
                    bid = b.get("id")
                    if not bid or bid in by_id:
                        continue
                    by_id[bid] = {
                        "yelp_id": bid,
                        "name": b.get("name", ""),
                        "category": cat,
                        "website": "",
                        "yelp_url": b.get("url", ""),
                        "phone": b.get("display_phone", ""),
                        "address": ", ".join(b.get("location", {}).get("display_address", [])),
                        "town": town,
                        "email": "",
                    }
                    added += 1
            if done % 20 == 0:
                print(f"  [{done}/{total}] +{added:2d} {town:18s} {cat:14s} total={len(by_id)} usage={usage}")
                RAW_CACHE.write_text(json.dumps(by_id))
            time.sleep(0.2)  # gentle pace
    RAW_CACHE.write_text(json.dumps(by_id))
    bump_usage(usage - get_usage())
    return by_id


def main() -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    biz = sweep()
    print(f"\n✓ Yelp sweep: {len(biz)} unique businesses")
    # NOTE: Yelp Fusion free tier doesn't give us website directly.
    # We'd need /businesses/{id} details call for each (1 call/biz = expensive).
    # Instead: we dump leads with phone + yelp_url and later enrich via other sources.

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "yelp_id", "name", "category", "website", "yelp_url",
            "phone", "address", "town", "email",
        ])
        w.writeheader()
        for b in biz.values():
            w.writerow(b)

    print(f"\n✅ {OUT_CSV}")
    print(f"   Yelp total: {len(biz)} businesses (phone + address, no direct email)")
    print(f"   Use these for phone outreach / enrichment via Apollo/Hunter.")


if __name__ == "__main__":
    main()
