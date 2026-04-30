"""
Find bar contacts city-by-city across the top 50 US cocktail cities.
Targets: Bar Managers, Beverage Directors, Head Bartenders, F&B Directors, Owners.
Saves to outreach/targets/bars_nationwide.json with deduplication.
"""
import anthropic, os, json, re, time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

OUTPUT_FILE = Path('outreach/targets/bars_nationwide.json')

# Top 50 US cities for cocktail culture, ordered by scene strength
CITIES = [
    # Tier 1 — Elite cocktail scenes
    "New York City, NY",
    "Chicago, IL",
    "Los Angeles, CA",
    "San Francisco, CA",
    "New Orleans, LA",
    "Portland, OR",
    "Seattle, WA",
    "Austin, TX",
    "Nashville, TN",
    "Miami, FL",
    # Tier 2 — Strong cocktail scenes
    "Denver, CO",
    "Houston, TX",
    "Philadelphia, PA",
    "Washington, DC",
    "San Diego, CA",
    "Atlanta, GA",
    "Boston, MA",
    "Dallas, TX",
    "Minneapolis, MN",
    "Louisville, KY",
    # Tier 3 — Growing cocktail scenes
    "Detroit, MI",
    "Kansas City, MO",
    "Charleston, SC",
    "Savannah, GA",
    "San Antonio, TX",
    "Las Vegas, NV",
    "Phoenix, AZ",
    "Tampa, FL",
    "Honolulu, HI",
    "Asheville, NC",
    # Tier 4 — Emerging
    "Pittsburgh, PA",
    "Oakland, CA",
    "Brooklyn, NY",
    "Tucson, AZ",
    "Raleigh, NC",
    "Richmond, VA",
    "St. Louis, MO",
    "Milwaukee, WI",
    "Columbus, OH",
    "Salt Lake City, UT",
    "Indianapolis, IN",
    "Omaha, NE",
    "Charlotte, NC",
    "Jacksonville, FL",
    "Sacramento, CA",
    "Cincinnati, OH",
    "Cleveland, OH",
    "Buffalo, NY",
    "Memphis, TN",
    "Birmingham, AL",
]

BARS_PER_CITY = 8  # Request 8 bars per city

# Load existing results to resume from where we left off
if OUTPUT_FILE.exists():
    all_results = json.loads(OUTPUT_FILE.read_text())
    print(f"Loaded {len(all_results)} existing contacts, resuming...")
else:
    all_results = []
seen_emails = set()
seen_names = set()
# Populate dedup sets from existing results
for c in all_results:
    e = (c.get('contact_email') or '').lower().strip()
    if e:
        seen_emails.add(e)
    seen_names.add(f"{(c.get('bar_name') or '').lower()}|{(c.get('contact_name') or '').lower()}")
cities_done = set((c.get('city') or '') for c in all_results)


def dedupe_and_add(contacts):
    """Add contacts, skipping duplicates by email or org+name combo."""
    added = 0
    for c in contacts:
        email = (c.get('contact_email') or '').lower().strip()
        org_key = f"{(c.get('bar_name') or '').lower()}|{(c.get('contact_name') or '').lower()}"

        if email and email in seen_emails:
            continue
        if org_key in seen_names:
            continue

        if email:
            seen_emails.add(email)
        seen_names.add(org_key)
        all_results.append(c)
        added += 1
    return added


print(f"\n🍸 Finding bar contacts across {len(CITIES)} US cities...\n")

for i, city in enumerate(CITIES, 1):
    if city in cities_done:
        print(f"  [{i:2d}/{len(CITIES)}] — {city:<25} already done, skipping")
        continue
    prompt = f"""List {BARS_PER_CITY} notable cocktail bars in {city} that would benefit from Spirit Library — a free cocktail app with 1,700+ recipes, custom menu builder, and staff training tools.

For each bar, provide the best contact person (Bar Manager, Beverage Director, Head Bartender, F&B Director, or Owner).

Return ONLY a JSON array with this structure:
[
  {{
    "bar_name": "...",
    "city": "{city}",
    "website": "...",
    "contact_name": "first last or null",
    "contact_title": "Bar Manager / Beverage Director / Head Bartender / F&B Director / Owner",
    "contact_email": "email or null",
    "instagram": "@handle or null",
    "bar_style": "cocktail bar / speakeasy / hotel bar / tiki bar / etc",
    "notable_for": "one line about what makes them notable",
    "pitch_angle": "one sentence on why Spirit Library fits them specifically"
  }}
]

Focus on bars known for craft cocktails, creative menus, or strong bar programs. Include a mix of independent bars, hotel bars, and bar groups. Infer emails from standard patterns (firstname@domain.com, info@domain.com) when not publicly known."""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = ""
        for block in resp.content:
            if hasattr(block, "text") and block.text.strip():
                text = block.text

        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            contacts = json.loads(match.group())
            for c in contacts:
                c['researched_at'] = datetime.utcnow().isoformat()
                c['source'] = 'claude_haiku_city_scan'
            added = dedupe_and_add(contacts)
            print(f"  [{i:2d}/{len(CITIES)}] ✓ {city:<25} found {len(contacts)}, added {added} (total: {len(all_results)})")
        else:
            print(f"  [{i:2d}/{len(CITIES)}] ? {city:<25} no JSON returned")

        time.sleep(3)
    except Exception as e:
        print(f"  [{i:2d}/{len(CITIES)}] ✗ {city}: {e}")
        time.sleep(5)

# Save results
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE.write_text(json.dumps(all_results, indent=2))

# Summary stats
cities_covered = len(set(c['city'] for c in all_results))
with_email = sum(1 for c in all_results if c.get('contact_email'))
by_title = {}
for c in all_results:
    t = c.get('contact_title', 'Unknown')
    by_title[t] = by_title.get(t, 0) + 1

print(f"\n{'='*60}")
print(f"✅ {len(all_results)} bar contacts across {cities_covered} cities → {OUTPUT_FILE}")
print(f"   With email: {with_email} | Without: {len(all_results) - with_email}")
print(f"   By title:")
for title, count in sorted(by_title.items(), key=lambda x: -x[1]):
    print(f"     {title}: {count}")
print(f"{'='*60}")
