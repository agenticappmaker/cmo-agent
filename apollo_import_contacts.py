"""
Apollo CSV Import Script — reads exported Apollo CSVs, deduplicates against
existing contacts, and saves a unified apollo_imported.json + .csv.

Usage:
    python apollo_import_contacts.py
"""

import csv
import json
import os
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
OUTREACH_DIR = SCRIPT_DIR / "outreach"
EXPORTS_DIR = OUTREACH_DIR / "apollo_exports"
OUTPUT_DIR = OUTREACH_DIR / "apollo_contacts"
TARGETS_DIR = OUTREACH_DIR / "targets"
SCRAPED_DIR = OUTREACH_DIR / "scraped_contacts"

OUTPUT_JSON = OUTPUT_DIR / "apollo_imported.json"
OUTPUT_CSV = OUTPUT_DIR / "apollo_imported.csv"


def load_existing_emails() -> set[str]:
    """Load emails from targets/ and scraped_contacts/ for dedup."""
    emails: set[str] = set()

    for directory in [TARGETS_DIR, SCRAPED_DIR]:
        if not directory.exists():
            continue
        for fp in directory.iterdir():
            if fp.suffix != ".json":
                continue
            try:
                data = json.loads(fp.read_text())
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    # Could be a dict with a list value
                    items = []
                    for v in data.values():
                        if isinstance(v, list):
                            items.extend(v)
                else:
                    continue
                for item in items:
                    if isinstance(item, dict):
                        for key in ("email", "Email", "emails"):
                            val = item.get(key, "")
                            if isinstance(val, str) and val:
                                emails.add(val.lower().strip())
                            elif isinstance(val, list):
                                for e in val:
                                    if isinstance(e, str) and e:
                                        emails.add(e.lower().strip())
            except (json.JSONDecodeError, Exception):
                continue

    return emails


def parse_apollo_csv(csv_path: Path) -> list[dict]:
    """Parse a single Apollo CSV export into contact dicts."""
    contacts = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                first = row.get("First Name", "").strip()
                last = row.get("Last Name", "").strip()
                name = f"{first} {last}".strip() or row.get("Name", "").strip()

                email = (row.get("Email", "")
                         or row.get("email", "")
                         or row.get("Work Email", "")
                         or row.get("Personal Email", "")).strip()

                title = (row.get("Title", "")
                         or row.get("Job Title", "")).strip()

                company = (row.get("Company", "")
                           or row.get("Organization Name", "")
                           or row.get("Company Name", "")).strip()

                city = (row.get("City", "")
                        or row.get("Person City", "")).strip()

                state = (row.get("State", "")
                         or row.get("Person State", "")).strip()

                linkedin = row.get("LinkedIn Url", row.get("Person Linkedin Url", "")).strip()

                if not name and not email:
                    continue

                contacts.append({
                    "name": name,
                    "email": email,
                    "title": title,
                    "company": company,
                    "city": city,
                    "state": state,
                    "linkedin": linkedin,
                    "source_file": csv_path.name,
                })
    except Exception as e:
        print(f"  [ERROR] {csv_path.name}: {e}")

    return contacts


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- Load existing contacts for dedup ---
    existing_emails = load_existing_emails()
    print(f"Loaded {len(existing_emails)} existing emails for dedup")

    # --- Parse all Apollo CSV exports ---
    if not EXPORTS_DIR.exists() or not list(EXPORTS_DIR.glob("*.csv")):
        print(f"\nNo CSV files found in {EXPORTS_DIR}/")
        print("Export CSVs from Apollo first. Run apollo_scraper.py for URLs.")
        return

    all_contacts: list[dict] = []
    csv_files = sorted(EXPORTS_DIR.glob("*.csv"))
    print(f"\nFound {len(csv_files)} CSV file(s):\n")

    for csv_path in csv_files:
        contacts = parse_apollo_csv(csv_path)
        print(f"  {csv_path.name}: {len(contacts)} contacts")
        all_contacts.extend(contacts)

    print(f"\nTotal raw contacts: {len(all_contacts)}")

    # --- Deduplicate ---
    seen_emails: set[str] = set()
    unique: list[dict] = []
    skipped_existing = 0
    skipped_dup = 0
    no_email = 0

    for c in all_contacts:
        email = c["email"].lower().strip() if c["email"] else ""
        if not email:
            no_email += 1
            # Keep contacts without email but with a name (can still be useful)
            unique.append(c)
            continue
        if email in existing_emails:
            skipped_existing += 1
            continue
        if email in seen_emails:
            skipped_dup += 1
            continue
        seen_emails.add(email)
        unique.append(c)

    # --- Save JSON ---
    output_data = {
        "imported_at": datetime.now().isoformat(),
        "stats": {
            "total_raw": len(all_contacts),
            "unique_imported": len(unique),
            "skipped_existing": skipped_existing,
            "skipped_duplicate": skipped_dup,
            "no_email": no_email,
        },
        "contacts": unique,
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(output_data, f, indent=2)

    # --- Save CSV ---
    if unique:
        fieldnames = ["name", "email", "title", "company", "city", "state", "linkedin", "source_file"]
        with open(OUTPUT_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(unique)

    # --- Stats ---
    print(f"\n{'=' * 50}")
    print(f"IMPORT STATS")
    print(f"{'=' * 50}")
    print(f"  CSV files processed:     {len(csv_files)}")
    print(f"  Total raw contacts:      {len(all_contacts)}")
    print(f"  Skipped (already known): {skipped_existing}")
    print(f"  Skipped (duplicate):     {skipped_dup}")
    print(f"  No email (kept anyway):  {no_email}")
    print(f"  Unique imported:         {len(unique)}")
    print(f"\nSaved to:")
    print(f"  JSON: {OUTPUT_JSON}")
    print(f"  CSV:  {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
