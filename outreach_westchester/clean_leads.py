"""
Post-process westchester_leads.csv:
- Lowercase emails, URL-decode, strip whitespace
- Drop invalid/obvious-noise addresses
- Dedupe by email (keep first occurrence)
- Write westchester_leads_clean.csv
"""
import csv, re, urllib.parse
from pathlib import Path

IN_CSV = Path(__file__).resolve().parent / "targets" / "westchester_leads.csv"
OUT_CSV = Path(__file__).resolve().parent / "targets" / "westchester_leads_clean.csv"

VALID = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
BLOCK_LOCAL = {
    # Totally useless / transactional / obvious non-targets
    "info@sentry.io", "noreply@wix.com",
}
BLOCK_SUBSTR = (
    "godaddy", "wixpress", "sentry.io", "wixstatic", "squarespace.com",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    "@sentry", "@example.com", "u003c", "u003e", "{{", "}}",
)

rows_in = list(csv.DictReader(open(IN_CSV)))
seen_emails = set()
clean = []
dropped = 0
for r in rows_in:
    raw = (r.get("email") or "").strip()
    if not raw:
        continue
    # URL-decode + strip + lowercase
    e = urllib.parse.unquote(raw).strip().lower()
    # Some sites concatenate text+email — grab the substring that's actually an email
    m = re.search(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", e)
    if not m:
        dropped += 1
        continue
    e = m.group(0)
    if not VALID.match(e):
        dropped += 1
        continue
    if e in BLOCK_LOCAL or any(b in e for b in BLOCK_SUBSTR):
        dropped += 1
        continue
    if e in seen_emails:
        continue
    seen_emails.add(e)
    r["email"] = e
    clean.append(r)

with open(OUT_CSV, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows_in[0].keys())
    w.writeheader()
    for r in clean:
        w.writerow(r)

print(f"In:      {len(rows_in)} rows")
print(f"Dropped: {dropped} (invalid/junk)")
print(f"Deduped: {len(rows_in) - dropped - len(clean)}")
print(f"Out:     {len(clean)} unique valid emails → {OUT_CSV}")
