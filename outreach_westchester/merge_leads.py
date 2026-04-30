"""
Merge all scraped lead sources into a single master CSV, deduped + cleaned.
Sources:
  1. targets/westchester_leads_clean.csv  (Phase 1 — Google Places Westchester)
  2. targets/tier2_leads.csv              (Phase 2 — Google Places NYC/LI/CT/NJ/HV)
  3. targets/osm_100mi_leads.csv          (Phase 2 — OSM Overpass 100mi)

Dedupe key: normalized email. Keeps first occurrence (Westchester → Tier2 → OSM priority).
Applies email hygiene from clean_leads.py.

Output: targets/master_leads.csv
"""
import csv, re, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = [
    ("westchester", ROOT / "targets" / "westchester_leads_clean.csv"),
    ("tier2",       ROOT / "targets" / "tier2_leads.csv"),
    ("osm",         ROOT / "targets" / "osm_100mi_leads.csv"),
]
OUT = ROOT / "targets" / "master_leads.csv"

VALID = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
BLOCK_SUBSTR = (
    "godaddy", "wixpress", "sentry.io", "wixstatic", "squarespace.com",
    "@example.com", "u003c", "u003e", "{{", "}}",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
)
FIELDS = [
    "source", "name", "category", "town", "address", "website",
    "phone", "email",
]


def clean_email(raw: str) -> str:
    if not raw:
        return ""
    e = urllib.parse.unquote(raw).strip().lower()
    m = re.search(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", e)
    if not m:
        return ""
    e = m.group(0)
    if not VALID.match(e):
        return ""
    if any(b in e for b in BLOCK_SUBSTR):
        return ""
    return e


def normalize_row(src: str, row: dict) -> dict:
    return {
        "source":   src,
        "name":     row.get("name", "").strip(),
        "category": row.get("category", "").strip(),
        "town":     row.get("town", "").strip(),
        "address":  row.get("address", "").strip(),
        "website":  row.get("website", "").strip(),
        "phone":    row.get("phone", "").strip(),
        "email":    clean_email(row.get("email", "")),
    }


def main() -> None:
    seen: set[str] = set()
    rows: list[dict] = []
    per_source: dict[str, int] = {}

    for src, path in SOURCES:
        if not path.exists():
            print(f"  ⚠ {path.name} not found — skipping")
            per_source[src] = 0
            continue
        kept = 0
        with open(path) as f:
            for raw in csv.DictReader(f):
                row = normalize_row(src, raw)
                if not row["email"]:
                    continue
                if row["email"] in seen:
                    continue
                seen.add(row["email"])
                rows.append(row)
                kept += 1
        per_source[src] = kept
        print(f"  ✓ {src:12s} kept {kept:5d} unique emails from {path.name}")

    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Summary stats
    by_cat: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1

    print(f"\n{'='*60}")
    print(f"✅ {OUT}")
    print(f"   Total unique emails:  {len(rows)}")
    print(f"\n   By source:")
    for s, c in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"     {s:14s} {c}")
    print(f"\n   Top 15 categories:")
    for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])[:15]:
        print(f"     {k:20s} {v}")


if __name__ == "__main__":
    main()
