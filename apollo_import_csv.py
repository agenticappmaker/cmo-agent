"""
Import Apollo CSV exports into the bar outreach pipeline.
Reads all CSVs from outreach/apollo_exports/, deduplicates, merges with existing contacts,
and feeds them into the email campaign.
"""
import csv, json, os, glob
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

EXPORT_DIR = Path('outreach/apollo_exports')
EXISTING_FILE = Path('outreach/targets/bars_nationwide.json')
ENRICHED_FILE = Path('outreach/targets/bars_nationwide_enriched.json')
OUTPUT_FILE = Path('outreach/targets/bars_apollo_imported.json')
MERGED_FILE = Path('outreach/targets/bars_all_contacts.json')

# Apollo CSV column mappings (standard Apollo export format)
FIELD_MAP = {
    'First Name': 'first_name',
    'Last Name': 'last_name',
    'Title': 'contact_title',
    'Company': 'bar_name',
    'Company Name for Emails': 'bar_name',
    'Email': 'apollo_email',
    'Email Status': 'apollo_confidence',
    'City': 'city_raw',
    'State': 'state',
    'Country': 'country',
    'Website': 'website',
    'Company Linkedin Url': 'company_linkedin',
    'Person Linkedin Url': 'person_linkedin',
    'Industry': 'industry',
    'Keywords': 'keywords',
    '# Employees': 'employee_count',
    'Apollo Contact Id': 'apollo_person_id',
}


def load_existing():
    """Load all existing contacts for dedup."""
    all_emails = set()
    all_names = set()

    for f in [EXISTING_FILE, ENRICHED_FILE, OUTPUT_FILE]:
        if f.exists():
            contacts = json.loads(f.read_text())
            for c in contacts:
                e = (c.get('apollo_email') or c.get('contact_email') or '').lower().strip()
                if e:
                    all_emails.add(e)
                name_key = f"{(c.get('bar_name') or '').lower()}|{(c.get('contact_name') or '').lower()}"
                all_names.add(name_key)

    return all_emails, all_names


def parse_csv(filepath):
    """Parse one Apollo CSV export."""
    contacts = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Map Apollo columns to our format
            contact = {}
            for csv_col, our_field in FIELD_MAP.items():
                if csv_col in row and row[csv_col]:
                    contact[our_field] = row[csv_col].strip()

            # Build contact_name
            first = contact.pop('first_name', '')
            last = contact.pop('last_name', '')
            contact['contact_name'] = f"{first} {last}".strip() or None

            # Build city
            city = contact.pop('city_raw', '')
            state = contact.pop('state', '')
            if city and state:
                contact['city'] = f"{city}, {state}"
            elif city:
                contact['city'] = city

            # Only keep contacts with emails
            if not contact.get('apollo_email'):
                continue

            # Also set contact_email for backward compat
            contact['contact_email'] = contact['apollo_email']
            contact['source'] = 'apollo_csv_export'
            contact['imported_at'] = datetime.utcnow().isoformat()
            contact['imported_from'] = os.path.basename(filepath)

            contacts.append(contact)

    return contacts


def run():
    if not EXPORT_DIR.exists():
        EXPORT_DIR.mkdir(parents=True)
        print(f"Created {EXPORT_DIR}/")
        print(f"Place your Apollo CSV exports there, then run this again.")
        print(f"\nTo generate search URLs: ~/spirit_venv/bin/python apollo_search_urls.py")
        return

    csvs = sorted(glob.glob(str(EXPORT_DIR / '*.csv')))
    if not csvs:
        print(f"No CSV files found in {EXPORT_DIR}/")
        print(f"Export from Apollo, save CSVs there, then run this again.")
        print(f"\nTo generate search URLs: ~/spirit_venv/bin/python apollo_search_urls.py")
        return

    print(f"\n🔄 Importing {len(csvs)} Apollo CSV exports...\n")

    existing_emails, existing_names = load_existing()
    print(f"  Existing contacts: {len(existing_emails)} emails, {len(existing_names)} name combos")

    new_contacts = []
    dupes = 0
    total_parsed = 0

    for filepath in csvs:
        contacts = parse_csv(filepath)
        total_parsed += len(contacts)
        added = 0

        for c in contacts:
            email = c.get('apollo_email', '').lower().strip()
            name_key = f"{(c.get('bar_name') or '').lower()}|{(c.get('contact_name') or '').lower()}"

            if email in existing_emails or name_key in existing_names:
                dupes += 1
                continue

            existing_emails.add(email)
            existing_names.add(name_key)
            new_contacts.append(c)
            added += 1

        print(f"  ✓ {os.path.basename(filepath)}: {len(contacts)} rows, {added} new contacts")

    # Save Apollo imports
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(new_contacts, indent=2))

    # Merge ALL contacts into one master file for the email sender
    all_contacts = []
    for f in [EXISTING_FILE, ENRICHED_FILE, OUTPUT_FILE]:
        if f.exists():
            all_contacts.extend(json.loads(f.read_text()))

    # Dedupe the merged list
    seen = set()
    merged = []
    for c in all_contacts:
        email = (c.get('apollo_email') or c.get('contact_email') or '').lower().strip()
        if not email or email in seen:
            continue
        seen.add(email)
        merged.append(c)

    MERGED_FILE.write_text(json.dumps(merged, indent=2))

    # Summary
    print(f"\n{'='*60}")
    print(f"✅ Imported {len(new_contacts)} new contacts (skipped {dupes} dupes)")
    print(f"   Total parsed from CSVs: {total_parsed}")
    print(f"   New contacts saved: {OUTPUT_FILE}")
    print(f"   Master contact list: {MERGED_FILE} ({len(merged)} total)")
    print(f"{'='*60}")
    print(f"\nThe email sender will now use {MERGED_FILE}")
    print(f"Run: ~/spirit_venv/bin/python send_bar_emails.py")


if __name__ == '__main__':
    run()
