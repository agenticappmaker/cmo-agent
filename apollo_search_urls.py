"""
Generate Apollo search URLs for bar contacts — open in browser, export CSV, then run apollo_import_csv.py.
"""
import urllib.parse

BASE = "https://app.apollo.io/people"

CITIES = [
    "New York", "Chicago", "Los Angeles", "San Francisco", "New Orleans",
    "Portland", "Seattle", "Austin", "Nashville", "Miami", "Denver",
    "Houston", "Philadelphia", "Washington DC", "San Diego", "Atlanta",
    "Boston", "Dallas", "Minneapolis", "Louisville", "Detroit", "Kansas City",
    "Charleston", "Savannah", "San Antonio", "Las Vegas", "Phoenix", "Tampa",
    "Honolulu", "Asheville", "Pittsburgh", "Oakland", "Brooklyn", "Tucson",
    "Raleigh", "Richmond", "St. Louis", "Milwaukee", "Columbus", "Salt Lake City",
    "Indianapolis", "Omaha", "Charlotte", "Jacksonville", "Sacramento",
    "Cincinnati", "Cleveland", "Buffalo", "Memphis", "Birmingham",
]

TITLES = [
    "Bar Manager", "Beverage Director", "Head Bartender",
    "F&B Director", "Bar Director", "Mixologist",
    "General Manager", "Owner"
]

INDUSTRIES = ["Restaurants", "Food & Beverages", "Hospitality"]

print("=" * 60)
print("APOLLO SEARCH URLS — Bar Outreach Campaign")
print("=" * 60)
print()
print("Instructions:")
print("1. Open each URL in your browser (you're logged into Apollo)")
print("2. Click 'Select All' → 'Export' → CSV")
print("3. Save all CSVs to ~/cmo-agent/outreach/apollo_exports/")
print("4. Run: ~/spirit_venv/bin/python apollo_import_csv.py")
print()
print("-" * 60)

# Generate 5 regional batch URLs (Apollo works best with ~10 cities per search)
batches = [CITIES[i:i+10] for i in range(0, len(CITIES), 10)]

for i, batch in enumerate(batches, 1):
    params = {
        "personTitles[]": TITLES,
        "organizationIndustryTagIds[]": INDUSTRIES,
        "personLocations[]": [f"{c}, US" for c in batch],
        "qKeywords": "cocktail OR bar OR mixology OR speakeasy",
        "organizationNumEmployeesRanges[]": ["1,200"],
    }

    # Build URL manually since Apollo uses repeated params
    parts = []
    for key, vals in params.items():
        if isinstance(vals, list):
            for v in vals:
                parts.append(f"{urllib.parse.quote(key)}={urllib.parse.quote(str(v))}")
        else:
            parts.append(f"{urllib.parse.quote(key)}={urllib.parse.quote(str(vals))}")

    url = f"{BASE}?{'&'.join(parts)}"

    print(f"\nBatch {i}: {', '.join(batch[:3])}... ({len(batch)} cities)")
    print(f"  Save as: apollo_batch_{i}.csv")
    print(f"  {url}")

print()
print("-" * 60)
print(f"\nTotal: {len(batches)} searches covering {len(CITIES)} cities")
print(f"After exporting, run: ~/spirit_venv/bin/python apollo_import_csv.py")
