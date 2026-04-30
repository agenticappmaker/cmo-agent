"""
Apollo Search URL Generator for Cocktail/Bar Industry Contacts.

Generates targeted Apollo.io search URLs that Steven can open in a browser
to export CSVs. Also checks for existing Apollo CSV exports and parses them.

Usage:
    python apollo_scraper.py
"""

import json
import csv
import os
import urllib.parse
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
OUTREACH_DIR = SCRIPT_DIR / "outreach"
URLS_FILE = OUTREACH_DIR / "apollo_search_urls.json"
EXPORTS_DIR = OUTREACH_DIR / "apollo_exports"

BASE_URL = "https://app.apollo.io/people"

CITIES = [
    "New York", "Los Angeles", "Chicago", "Miami", "San Francisco",
    "Austin", "Nashville", "Seattle", "Portland", "Denver",
]

TITLE_GROUPS = {
    "bartenders": [
        "Bartender", "Head Bartender", "Mixologist", "Bar Manager",
        "Lead Bartender", "Senior Bartender",
    ],
    "fb_directors": [
        "Food and Beverage Director", "F&B Director", "F&B Manager",
        "Beverage Director", "Beverage Manager", "Director of Beverage",
    ],
    "bar_owners": [
        "Bar Owner", "Restaurant Owner", "Proprietor", "Owner",
        "Co-Owner", "Founder",
    ],
}

INDUSTRIES = [
    "Wine & Spirits", "Food & Beverages", "Restaurants", "Hospitality",
]

KEYWORDS = "cocktail OR bar OR mixology OR speakeasy OR spirits"


# ---------------------------------------------------------------------------
# URL generation
# ---------------------------------------------------------------------------

def build_apollo_url(titles: list[str], cities: list[str],
                     industries: list[str] | None = None,
                     keywords: str | None = None,
                     employee_range: str = "1,500") -> str:
    """Build an Apollo people-search URL with repeated query params."""
    parts: list[str] = []

    for t in titles:
        parts.append(f"personTitles[]={urllib.parse.quote(t)}")
    for c in cities:
        parts.append(f"personLocations[]={urllib.parse.quote(f'{c}, US')}")
    if industries:
        for ind in industries:
            parts.append(f"organizationIndustryTagIds[]={urllib.parse.quote(ind)}")
    if keywords:
        parts.append(f"qKeywords={urllib.parse.quote(keywords)}")
    parts.append(f"organizationNumEmployeesRanges[]={urllib.parse.quote(employee_range)}")

    return f"{BASE_URL}?{'&'.join(parts)}"


def generate_search_urls() -> list[dict]:
    """Generate 20 Apollo search URLs across title groups and cities."""
    urls: list[dict] = []
    url_id = 0

    # Strategy: for each title group, create city batches
    # 3 title groups x 5 city pairs = 15 URLs
    city_pairs = [CITIES[i:i + 2] for i in range(0, len(CITIES), 2)]

    for group_name, titles in TITLE_GROUPS.items():
        for pair in city_pairs:
            url_id += 1
            url = build_apollo_url(titles, pair, INDUSTRIES, KEYWORDS)
            urls.append({
                "id": url_id,
                "group": group_name,
                "cities": pair,
                "titles": titles,
                "url": url,
                "suggested_filename": f"apollo_{group_name}_{pair[0].lower().replace(' ', '_')}.csv",
            })

    # 5 more: industry-wide searches (all titles, one city each, broader scope)
    all_titles = [t for group in TITLE_GROUPS.values() for t in group]
    for city in CITIES[:5]:
        url_id += 1
        url = build_apollo_url(all_titles, [city], INDUSTRIES, KEYWORDS)
        urls.append({
            "id": url_id,
            "group": "all_titles",
            "cities": [city],
            "titles": all_titles,
            "url": url,
            "suggested_filename": f"apollo_all_{city.lower().replace(' ', '_')}.csv",
        })

    return urls


# ---------------------------------------------------------------------------
# CSV parsing (existing exports)
# ---------------------------------------------------------------------------

def parse_apollo_csvs(exports_dir: Path) -> list[dict]:
    """Read all CSVs in exports_dir and return unified contact list."""
    contacts: list[dict] = []
    if not exports_dir.exists():
        return contacts

    csv_files = list(exports_dir.glob("*.csv"))
    if not csv_files:
        return contacts

    print(f"\nFound {len(csv_files)} existing Apollo CSV export(s):")

    for csv_path in csv_files:
        print(f"  - {csv_path.name}")
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Apollo CSV columns vary; try common field names
                    contact = {
                        "name": (row.get("First Name", "") + " " + row.get("Last Name", "")).strip()
                               or row.get("Name", "").strip(),
                        "email": row.get("Email", row.get("email", "")).strip(),
                        "title": row.get("Title", row.get("Job Title", "")).strip(),
                        "company": row.get("Company", row.get("Organization Name", "")).strip(),
                        "city": row.get("City", row.get("Person City", "")).strip(),
                        "source": f"apollo_export:{csv_path.name}",
                    }
                    if contact["name"] or contact["email"]:
                        contacts.append(contact)
        except Exception as e:
            print(f"    [ERROR] Could not parse {csv_path.name}: {e}")

    return contacts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUTREACH_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Generate search URLs
    urls = generate_search_urls()
    with open(URLS_FILE, "w") as f:
        json.dump({
            "generated": datetime.now().isoformat(),
            "total_urls": len(urls),
            "searches": urls,
        }, f, indent=2)

    print("=" * 60)
    print("APOLLO SEARCH URL GENERATOR — Bar/Cocktail Industry")
    print("=" * 60)
    print(f"\nGenerated {len(urls)} search URLs -> {URLS_FILE}")
    print()

    for entry in urls:
        print(f"  [{entry['id']:2d}] {entry['group']:15s} | {', '.join(entry['cities']):30s}")
        print(f"       Save as: {entry['suggested_filename']}")
        print(f"       {entry['url'][:120]}...")
        print()

    # 2. Check for existing CSV exports
    contacts = parse_apollo_csvs(EXPORTS_DIR)
    if contacts:
        print(f"\nParsed {len(contacts)} contacts from existing exports.")
        # Quick dedup by email
        seen = set()
        unique = []
        for c in contacts:
            key = c["email"].lower() if c["email"] else c["name"].lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(c)
        print(f"After dedup: {len(unique)} unique contacts.")

        # Save unified list
        unified_path = OUTREACH_DIR / "apollo_contacts_unified.json"
        with open(unified_path, "w") as f:
            json.dump(unique, f, indent=2)
        print(f"Saved to {unified_path}")
    else:
        print("\nNo existing Apollo CSV exports found in:")
        print(f"  {EXPORTS_DIR}/")
        print("  Export CSVs from the URLs above, save them there, then re-run.")

    print()
    print("Next steps:")
    print("  1. Open each URL in browser (logged into Apollo)")
    print("  2. Select All -> Export -> CSV")
    print(f"  3. Save CSVs to {EXPORTS_DIR}/")
    print("  4. Run: python apollo_import_contacts.py")


if __name__ == "__main__":
    main()
