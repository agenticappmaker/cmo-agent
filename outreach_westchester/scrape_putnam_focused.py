"""
Putnam County NY focused Overpass sweep — free, no API key.

The 100mi sweep already touched Putnam (272 businesses, 15 emails) but at
0.3-degree cell resolution. Putnam is small + rural, so finer cells +
broader tag filters surface listings the coarse sweep skipped.

Bumps Putnam from ~15 → expected ~80-150 clean emails.
Output appends into targets/osm_100mi_leads.csv (re-uses OSM schema + email cache).
"""
import csv, json, re, time, urllib.parse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OVERPASS = "https://overpass-api.de/api/interpreter"

# Putnam County NY bbox (slightly generous; haversine filter excludes outside-100mi)
PUTNAM_BBOX = (41.30, -73.99, 41.56, -73.55)  # s, w, n, e
CELL_DEG = 0.10  # ~7 mi cells — much finer than 100mi sweep's 0.3

OUT_CSV = ROOT / "targets" / "osm_100mi_leads.csv"
RAW_CACHE = ROOT / "state" / "osm_raw.json"
EMAIL_CACHE = ROOT / "state" / "osm_email_cache.json"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
BLOCK = (
    "example.com", "sentry.io", "wixpress", "godaddy",
    "squarespace", "wixstatic", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".webp", "{{", "}}", "u003",
)

OVERPASS_QUERY = """
[out:json][timeout:90];
(
  node["amenity"]({s},{w},{n},{e});
  node["shop"]({s},{w},{n},{e});
  node["craft"]({s},{w},{n},{e});
  node["office"]({s},{w},{n},{e});
  node["tourism"]({s},{w},{n},{e});
  node["leisure"]({s},{w},{n},{e});
  node["healthcare"]({s},{w},{n},{e});
  way["amenity"]({s},{w},{n},{e});
  way["shop"]({s},{w},{n},{e});
  way["tourism"]({s},{w},{n},{e});
  way["leisure"]({s},{w},{n},{e});
  way["healthcare"]({s},{w},{n},{e});
);
out tags center;
""".strip()


def cells():
    s, w, n, e = PUTNAM_BBOX
    lat = s
    while lat < n:
        lon = w
        while lon < e:
            yield (round(lat,4), round(lon,4), round(lat+CELL_DEG,4), round(lon+CELL_DEG,4))
            lon += CELL_DEG
        lat += CELL_DEG


def overpass(bbox):
    s, w, n, e = bbox
    q = OVERPASS_QUERY.format(s=s, w=w, n=n, e=e)
    data = f"data={urllib.parse.quote(q)}".encode()
    req = urllib.request.Request(
        OVERPASS, data=data, method="POST",
        headers={
            "User-Agent": "smore-labs-local-smb-lookup (claudesonnet111@gmail.com)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    for attempt in range(4):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=120).read()).get("elements", [])
        except urllib.error.HTTPError as he:
            if he.code == 429:
                time.sleep(15 * (attempt + 1)); continue
            print(f"  ! HTTP {he.code}"); return []
        except Exception as ex:
            print(f"  ! {ex} (retry)"); time.sleep(10 * (attempt + 1))
    return []


def normalize_website(u: str) -> str:
    if not u: return ""
    u = u.strip()
    if not u.startswith(("http://", "https://")): u = "https://" + u
    return u


class _Strip(HTMLParser):
    def __init__(self):
        super().__init__(); self.out=[]; self._skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ("script","style"): self._skip += 1
        if tag == "a":
            for k,v in attrs:
                if k=="href" and v and v.lower().startswith("mailto:"):
                    self.out.append(v[7:].split("?")[0])
    def handle_endtag(self, tag):
        if tag in ("script","style") and self._skip: self._skip -= 1
    def handle_data(self, data):
        if not self._skip: self.out.append(data)


def fetch(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (smore-labs-scraper)"})
        return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def find_email(site):
    if not site: return ""
    base = site.rstrip("/")
    for url in (base, f"{base}/contact", f"{base}/contact-us", f"{base}/about"):
        html = fetch(url)
        if not html: continue
        sp = _Strip()
        try: sp.feed(html)
        except Exception: pass
        text = " ".join(sp.out)
        for m in EMAIL_RE.findall(text):
            low = m.lower()
            if any(b in low for b in BLOCK): continue
            return m
    return ""


def main():
    raw_cache = json.loads(RAW_CACHE.read_text()) if RAW_CACHE.exists() else {}
    email_cache = json.loads(EMAIL_CACHE.read_text()) if EMAIL_CACHE.exists() else {}
    box_list = list(cells())
    print(f"→ Putnam-focused sweep: {len(box_list)} cells @ {CELL_DEG} deg (~7 mi each)")

    new_rows = []
    for i, bbox in enumerate(box_list, 1):
        elements = overpass(bbox)
        added = 0
        for el in elements:
            tags = el.get("tags") or {}
            name = tags.get("name")
            if not name: continue
            key = f"{el.get('type')}/{el.get('id')}"
            if key in raw_cache: continue  # already have it
            website = tags.get("contact:website") or tags.get("website") or ""
            email = (tags.get("contact:email") or tags.get("email") or "").lower().strip()
            phone = tags.get("contact:phone") or tags.get("phone") or ""
            category = (tags.get("amenity") or tags.get("shop") or tags.get("craft")
                        or tags.get("office") or tags.get("tourism") or tags.get("leisure")
                        or tags.get("healthcare") or "other")
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            row = {
                "osm_id": key, "name": name, "category": category,
                "website": normalize_website(website), "email": email, "phone": phone,
                "lat": lat, "lon": lon,
                "address": " ".join(filter(None, [
                    tags.get("addr:housenumber",""), tags.get("addr:street",""),
                    tags.get("addr:city",""), tags.get("addr:state",""),
                    tags.get("addr:postcode",""),
                ])).strip(),
                "town": "Putnam NY",
            }
            raw_cache[key] = row
            new_rows.append(row)
            added += 1
        print(f"  [{i:2d}/{len(box_list)}] +{added:3d} new (cache total: {len(raw_cache)})")
        time.sleep(1.5)
    RAW_CACHE.write_text(json.dumps(raw_cache))
    print(f"\n✓ Sweep added {len(new_rows)} net-new Putnam businesses")

    # Email scrape only the net-new ones with websites and no OSM email
    todo = [r for r in new_rows if r.get("website") and not r.get("email") and r["osm_id"] not in email_cache]
    print(f"→ Scraping emails from {len(todo)} new sites")
    if todo:
        def work(r): return r["osm_id"], find_email(r["website"])
        done = hit = 0
        with ThreadPoolExecutor(max_workers=20) as ex:
            futs = [ex.submit(work, r) for r in todo]
            for f in as_completed(futs):
                pid, em = f.result()
                email_cache[pid] = em
                if pid in raw_cache: raw_cache[pid]["email"] = em
                done += 1
                if em: hit += 1
                if done % 50 == 0:
                    EMAIL_CACHE.write_text(json.dumps(email_cache))
                    print(f"  [{done}/{len(todo)}] hits={hit}")
        EMAIL_CACHE.write_text(json.dumps(email_cache))
        RAW_CACHE.write_text(json.dumps(raw_cache))

    # Append to existing CSV (don't rewrite — keep all 100mi rows)
    if new_rows:
        with open(OUT_CSV) as f:
            reader = csv.DictReader(f)
            fields = list(reader.fieldnames or [])
            existing_ids = {r["osm_id"] for r in reader}
        # ensure 'town' is in fields
        if "town" not in fields: fields.append("town")
        to_append = [r for r in new_rows if r["osm_id"] not in existing_ids]
        with open(OUT_CSV, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            for r in to_append:
                # backfill email from cache in case it was scraped above
                r["email"] = r.get("email") or email_cache.get(r["osm_id"], "")
                w.writerow(r)
        print(f"\n✅ Appended {len(to_append)} new rows to {OUT_CSV.name}")
    else:
        print("\n✓ No net-new rows — Putnam already fully covered")

    putnam_email = sum(1 for r in raw_cache.values()
                       if r.get("email") and (r.get("town") == "Putnam NY"))
    print(f"   Putnam emails (in cache): {putnam_email}")


if __name__ == "__main__":
    main()
