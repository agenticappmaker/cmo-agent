"""
Deeper second-pass email scraper — free, no API.

The original osm scraper tries only /, /contact, /contact-us, /about and gives
up. This pass goes much further: 18 candidate paths + footer links + obfuscated
emails ("name [at] domain dot com"). Re-runs only on rows with a website but no
email yet. Uses a SEPARATE cache so it doesn't clobber the original.

Target: master_leads.csv has 7,489 emails in target counties; the OSM CSV has
~9,867 more rows in those counties with websites but no email. Realistic harvest:
1,500–3,000 additional clean emails.
"""
import csv, json, re, time, urllib.parse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OSM_CSV = ROOT / "targets" / "osm_100mi_leads.csv"
CACHE = ROOT / "state" / "deep_email_cache.json"

# County bboxes — only deep-scrape rows in target counties (free but slow,
# don't waste cycles on far-Hudson-Valley rows)
COUNTIES = [
    ("Putnam NY",     41.32, 41.55, -73.98, -73.55),
    ("Rockland NY",   41.00, 41.27, -74.25, -73.88),
    ("Westchester",   40.91, 41.36, -73.92, -73.48),
    ("Bronx",         40.79, 40.92, -73.93, -73.76),
    ("Manhattan",     40.70, 40.88, -74.02, -73.91),
    ("Bergen NJ",     40.79, 41.13, -74.30, -73.89),
    ("Fairfield CT",  41.04, 41.55, -73.73, -73.05),
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# Obfuscated forms: "name [at] domain.com", "name (at) domain dot com", "name AT domain DOT com"
OBFUSC_RE = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*[\(\[]?\s*(?:at|AT|@)\s*[\)\]]?\s*([a-zA-Z0-9.\-]+)"
    r"\s*[\(\[]?\s*(?:dot|DOT|\.)\s*[\)\]]?\s*([a-zA-Z]{2,})",
)
BLOCK = (
    "example.com", "yourdomain", "sentry.io", "wixpress", "godaddy",
    "squarespace", "wixstatic", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".webp", "{{", "}}", "u003", "test@test", "you@", "name@",
    "email@", "mail@example",
)

CANDIDATE_PATHS = [
    "", "/contact", "/contact-us", "/contactus", "/about", "/about-us",
    "/info", "/team", "/staff", "/our-team", "/locations", "/location",
    "/get-in-touch", "/reach-us", "/enquiry", "/enquiries", "/inquiries",
    "/book", "/booking", "/reservations", "/menu", "/footer",
]


def in_target(lat, lon):
    for name,s,n,w,e in COUNTIES:
        if s<=lat<=n and w<=lon<=e:
            return name
    return None


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


def fetch(url, timeout=8):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (smore-labs-scraper)"})
        return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def extract(text):
    """Return first clean email from raw text+mailtos, including deobfuscated."""
    for m in EMAIL_RE.findall(text):
        low = m.lower()
        if any(b in low for b in BLOCK): continue
        if low.startswith("u003") or "%40" in low: continue
        return m
    for u, d, t in OBFUSC_RE.findall(text):
        candidate = f"{u}@{d}.{t}".lower()
        if any(b in candidate for b in BLOCK): continue
        if EMAIL_RE.fullmatch(candidate):
            return candidate
    return ""


def deep_find_email(site):
    if not site: return ""
    base = site.rstrip("/")
    for path in CANDIDATE_PATHS:
        url = base + path
        html = fetch(url)
        if not html: continue
        sp = _Strip()
        try: sp.feed(html)
        except Exception: pass
        text = " ".join(sp.out)
        em = extract(text)
        if em: return em
    return ""


def main():
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = []
    with open(OSM_CSV) as f:
        for r in csv.DictReader(f):
            if r.get("email"): continue
            site = (r.get("website") or "").strip()
            if not site: continue
            try: lat=float(r["lat"]); lon=float(r["lon"])
            except: continue
            county = in_target(lat, lon)
            if not county: continue
            if r["osm_id"] in cache: continue
            todo.append(r)
    print(f"→ Deep email scrape on {len(todo)} OSM rows in target counties (already cached: {len(cache)})")
    if not todo:
        print("✓ Nothing left to do")
        return

    def work(r): return r["osm_id"], deep_find_email(r["website"])
    done = hit = 0
    start = time.time()
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs = [ex.submit(work, r) for r in todo]
        for f in as_completed(futs):
            pid, em = f.result()
            cache[pid] = em
            done += 1
            if em: hit += 1
            if done % 200 == 0:
                CACHE.write_text(json.dumps(cache))
                rate = done / max(1, time.time()-start)
                eta = (len(todo)-done) / max(0.001, rate)
                print(f"  [{done}/{len(todo)}] hits={hit}  rate={rate:.1f}/s  ETA {eta:.0f}s")
    CACHE.write_text(json.dumps(cache))
    print(f"\n✓ Deep scrape: {hit} new emails harvested from {len(todo)} sites ({100*hit/len(todo):.1f}%)")

    # Apply harvested emails back to the OSM CSV
    rows = []
    with open(OSM_CSV) as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        for r in reader:
            if not r.get("email") and r["osm_id"] in cache and cache[r["osm_id"]]:
                r["email"] = cache[r["osm_id"]]
            rows.append(r)
    with open(OSM_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"✅ Wrote enriched OSM CSV — re-run merge_leads.py to update master")


if __name__ == "__main__":
    main()
