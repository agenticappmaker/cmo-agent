"""
Backfill county/area into OSM rows that have lat/lon but blank `town`.
Free — no API. Uses bounding-box lookup against target counties.

Why: scrape_osm_100mi.py covers 100mi around White Plains (already includes
Putnam, Rockland, Westchester, Bronx, Manhattan, Bergen NJ, Fairfield CT) but
addr:city wasn't always tagged in OSM, so the rows show empty `town` and the
Agency OS grader can't bucket them by geographic_fit.

Output: rewrites targets/osm_100mi_leads.csv in place with `town` populated
where the lat/lon falls inside one of the county bboxes. Other rows kept as-is.
"""
import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "targets" / "osm_100mi_leads.csv"
BACKUP = ROOT / "targets" / "osm_100mi_leads.bak.csv"

# (south, north, west, east) — slightly generous bboxes
COUNTIES = [
    ("Putnam NY",     41.32, 41.55, -73.98, -73.55),
    ("Rockland NY",   41.00, 41.27, -74.25, -73.88),
    ("Westchester",   40.91, 41.36, -73.92, -73.48),
    ("Bronx",         40.79, 40.92, -73.93, -73.76),
    ("Manhattan",     40.70, 40.88, -74.02, -73.91),
    ("Bergen NJ",     40.79, 41.13, -74.30, -73.89),
    ("Fairfield CT",  41.04, 41.55, -73.73, -73.05),
]


def county_for(lat: float, lon: float) -> str:
    for name, s, n, w, e in COUNTIES:
        if s <= lat <= n and w <= lon <= e:
            return name
    return ""


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}")
    if not BACKUP.exists():
        shutil.copy2(SRC, BACKUP)

    rows = []
    with open(SRC) as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        if "town" not in fields:
            fields.append("town")
        for r in reader:
            try:
                lat = float(r.get("lat") or "")
                lon = float(r.get("lon") or "")
            except ValueError:
                rows.append(r)
                continue
            if not r.get("town"):
                r["town"] = county_for(lat, lon)
            rows.append(r)

    with open(SRC, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    bucket = {c[0]: 0 for c in COUNTIES}
    bucket_email = {c[0]: 0 for c in COUNTIES}
    for r in rows:
        t = r.get("town") or ""
        if t in bucket:
            bucket[t] += 1
            if r.get("email"):
                bucket_email[t] += 1
    print(f"✅ Backfilled town on {SRC}")
    print(f"{'County':<14s} {'Total':>10s} {'WithEmail':>10s}")
    for k, v in bucket.items():
        print(f"{k:<14s} {v:>10,d} {bucket_email[k]:>10,d}")


if __name__ == "__main__":
    main()
