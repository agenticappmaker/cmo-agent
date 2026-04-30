"""
Enrich existing bar contacts with verified emails via Apollo.io API.
Reads bars_nationwide.json, searches Apollo for verified emails, and saves enriched results.
"""
import json, os, time, requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")
BASE_URL = "https://api.apollo.io/api/v1"

CONTACTS_FILE = Path("outreach/targets/bars_nationwide.json")
ENRICHED_FILE = Path("outreach/targets/bars_nationwide_enriched.json")
NEW_LEADS_FILE = Path("outreach/targets/bars_apollo_new_leads.json")

TARGET_TITLES = [
    "Bar Manager", "Beverage Director", "Head Bartender",
    "F&B Director", "Owner", "General Manager",
    "Beverage Manager", "Lead Bartender", "Bar Director",
]

TARGET_INDUSTRIES = ["Restaurants", "Hospitality", "Food & Beverage"]

RATE_LIMIT_DELAY = 1.0  # seconds between requests


def apollo_headers():
    return {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": APOLLO_API_KEY,
    }


def search_person(contact_name, company_name):
    """Search Apollo for a person by name and company."""
    parts = contact_name.strip().split() if contact_name else []
    if len(parts) < 2:
        return None

    payload = {
        "api_key": APOLLO_API_KEY,
        "q_organization_name": company_name or "",
        "person_titles": TARGET_TITLES,
        "person_locations": ["United States"],
        "page": 1,
        "per_page": 5,
    }

    # Add name filters
    payload["first_name"] = parts[0]
    payload["last_name"] = " ".join(parts[1:])

    try:
        resp = requests.post(f"{BASE_URL}/mixed_people/search", json=payload, headers=apollo_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()

        people = data.get("people", [])
        if not people:
            return None

        # Return best match
        for person in people:
            email = person.get("email")
            if email:
                return {
                    "apollo_email": email,
                    "apollo_confidence": person.get("email_confidence", None),
                    "apollo_person_id": person.get("id"),
                    "apollo_name": person.get("name"),
                    "apollo_title": person.get("title"),
                    "apollo_org": person.get("organization", {}).get("name") if person.get("organization") else None,
                }
        return None

    except requests.RequestException as e:
        print(f"    API error (person search): {e}")
        return None


def search_org_then_people(company_name):
    """Fallback: search for the organization, then find people at it."""
    if not company_name:
        return None, []

    # Step 1: find the organization
    payload = {
        "api_key": APOLLO_API_KEY,
        "q_organization_name": company_name,
        "organization_locations": ["United States"],
        "page": 1,
        "per_page": 5,
    }

    try:
        resp = requests.post(f"{BASE_URL}/mixed_companies/search", json=payload, headers=apollo_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        orgs = data.get("organizations", []) or data.get("accounts", [])
        if not orgs:
            return None, []

        org = orgs[0]
        org_id = org.get("id")
        if not org_id:
            return None, []

        time.sleep(RATE_LIMIT_DELAY)

        # Step 2: find people at this organization
        people_payload = {
            "api_key": APOLLO_API_KEY,
            "organization_ids": [org_id],
            "person_titles": TARGET_TITLES,
            "page": 1,
            "per_page": 10,
        }

        resp2 = requests.post(f"{BASE_URL}/mixed_people/search", json=people_payload, headers=apollo_headers(), timeout=30)
        resp2.raise_for_status()
        data2 = resp2.json()
        people = data2.get("people", [])

        primary = None
        extras = []
        for person in people:
            email = person.get("email")
            if not email:
                continue
            info = {
                "apollo_email": email,
                "apollo_confidence": person.get("email_confidence"),
                "apollo_person_id": person.get("id"),
                "apollo_name": person.get("name"),
                "apollo_title": person.get("title"),
                "apollo_org": org.get("name"),
            }
            if primary is None:
                primary = info
            else:
                extras.append(info)

        return primary, extras

    except requests.RequestException as e:
        print(f"    API error (org search): {e}")
        return None, []


def run():
    if not APOLLO_API_KEY:
        print("ERROR: APOLLO_API_KEY not set in .env")
        return

    if not CONTACTS_FILE.exists():
        print(f"ERROR: {CONTACTS_FILE} not found. Run find_bars_nationwide.py first.")
        return

    contacts = json.loads(CONTACTS_FILE.read_text())
    print(f"\nApollo Enrichment: {len(contacts)} bar contacts\n")

    # Load existing enriched data for resume support
    enriched = []
    if ENRICHED_FILE.exists():
        enriched = json.loads(ENRICHED_FILE.read_text())

    enriched_map = {c.get("contact_email", "").lower(): c for c in enriched if c.get("contact_email")}
    # Also index by bar_name for contacts without email
    for c in enriched:
        if c.get("apollo_email"):
            enriched_map[c["bar_name"].lower()] = c

    new_leads = []
    if NEW_LEADS_FILE.exists():
        new_leads = json.loads(NEW_LEADS_FILE.read_text())
    new_leads_emails = {l.get("apollo_email", "").lower() for l in new_leads if l.get("apollo_email")}

    stats = {"enriched": 0, "skipped": 0, "failed": 0, "new_leads": 0}

    for i, contact in enumerate(contacts):
        bar = contact.get("bar_name", "Unknown")
        email_key = (contact.get("contact_email") or "").lower()

        # Resume support: skip if already enriched
        existing = enriched_map.get(email_key) or enriched_map.get(bar.lower())
        if existing and existing.get("apollo_email"):
            stats["skipped"] += 1
            continue

        print(f"  [{i+1}/{len(contacts)}] {bar} — {contact.get('contact_name', 'N/A')}")

        # Try person search first
        result = search_person(contact.get("contact_name"), bar)
        time.sleep(RATE_LIMIT_DELAY)

        extras = []
        if not result:
            # Fallback to org search
            print(f"    No person match, trying org search...")
            result, extras = search_org_then_people(bar)
            time.sleep(RATE_LIMIT_DELAY)

        # Update contact
        enriched_contact = dict(contact)
        if result:
            enriched_contact["apollo_email"] = result["apollo_email"]
            enriched_contact["apollo_confidence"] = result["apollo_confidence"]
            enriched_contact["apollo_person_id"] = result["apollo_person_id"]
            enriched_contact["apollo_enriched_at"] = datetime.utcnow().isoformat()
            print(f"    -> {result['apollo_email']} (confidence: {result['apollo_confidence']})")
            stats["enriched"] += 1
        else:
            enriched_contact["apollo_enriched_at"] = datetime.utcnow().isoformat()
            enriched_contact["apollo_email"] = None
            print(f"    -> No verified email found")
            stats["failed"] += 1

        # Update enriched map and list
        enriched_map[email_key or bar.lower()] = enriched_contact

        # Save any extra people as new leads
        for extra in extras:
            if extra["apollo_email"].lower() not in new_leads_emails:
                new_lead = {
                    "bar_name": bar,
                    "city": contact.get("city", ""),
                    "website": contact.get("website", ""),
                    "contact_name": extra.get("apollo_name", ""),
                    "contact_title": extra.get("apollo_title", ""),
                    "contact_email": extra["apollo_email"],
                    "instagram": contact.get("instagram", ""),
                    "bar_style": contact.get("bar_style", ""),
                    "notable_for": contact.get("notable_for", ""),
                    "pitch_angle": contact.get("pitch_angle", ""),
                    "researched_at": datetime.utcnow().isoformat(),
                    "source": "apollo_enrichment_extra",
                    "apollo_email": extra["apollo_email"],
                    "apollo_confidence": extra["apollo_confidence"],
                    "apollo_person_id": extra["apollo_person_id"],
                    "apollo_enriched_at": datetime.utcnow().isoformat(),
                }
                new_leads.append(new_lead)
                new_leads_emails.add(extra["apollo_email"].lower())
                stats["new_leads"] += 1

        # Save after each contact (resume support)
        enriched_list = list(enriched_map.values())
        ENRICHED_FILE.parent.mkdir(parents=True, exist_ok=True)
        ENRICHED_FILE.write_text(json.dumps(enriched_list, indent=2))
        if new_leads:
            NEW_LEADS_FILE.write_text(json.dumps(new_leads, indent=2))

    # Final summary
    print(f"\n{'='*60}")
    print(f"Apollo Enrichment Complete")
    print(f"  Enriched with verified email: {stats['enriched']}")
    print(f"  Skipped (already enriched):   {stats['skipped']}")
    print(f"  No email found:               {stats['failed']}")
    print(f"  New leads discovered:         {stats['new_leads']}")
    print(f"  Output: {ENRICHED_FILE}")
    if new_leads:
        print(f"  New leads: {NEW_LEADS_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    run()
