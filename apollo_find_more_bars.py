"""
Discover new bar contacts via Apollo.io Organization + People Search.
Finds bars beyond the initial 255 in bars_nationwide.json.
Target: up to 1,000 additional contacts.
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
DISCOVERY_FILE = Path("outreach/targets/bars_apollo_discovery.json")
STATE_FILE = Path("outreach/state/apollo_discovery_state.json")

TARGET_TITLES = [
    "Bar Manager", "Beverage Director", "Head Bartender",
    "F&B Director", "Owner", "General Manager",
    "Beverage Manager", "Lead Bartender", "Bar Director",
]

SEARCH_KEYWORDS = [
    "cocktail bar", "craft cocktails", "mixology", "speakeasy", "bar & lounge",
]

INDUSTRIES = ["Restaurants", "Food & Beverage Services", "Hospitality"]

TARGET_CONTACTS = 1000
RATE_LIMIT_DELAY = 1.0


def apollo_headers():
    return {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": APOLLO_API_KEY,
    }


def load_existing_emails():
    """Load all known emails for deduplication."""
    emails = set()
    org_names = set()
    for path in [CONTACTS_FILE, ENRICHED_FILE, DISCOVERY_FILE]:
        if path.exists():
            for c in json.loads(path.read_text()):
                for key in ["contact_email", "apollo_email"]:
                    e = (c.get(key) or "").lower().strip()
                    if e:
                        emails.add(e)
                name = (c.get("bar_name") or "").lower().strip()
                if name:
                    org_names.add(name)
    return emails, org_names


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"keyword_index": 0, "page": 1, "total_found": 0}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def search_orgs(keyword, page=1):
    """Search Apollo for bar organizations."""
    payload = {
        "api_key": APOLLO_API_KEY,
        "q_organization_keyword_tags": [keyword],
        "organization_industry_tag_ids": INDUSTRIES,
        "organization_num_employees_ranges": ["5,200"],
        "organization_locations": ["United States"],
        "page": page,
        "per_page": 25,
    }
    try:
        resp = requests.post(f"{BASE_URL}/mixed_companies/search", json=payload, headers=apollo_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        orgs = data.get("organizations", []) or data.get("accounts", [])
        total_pages = data.get("pagination", {}).get("total_pages", 1)
        return orgs, total_pages
    except requests.RequestException as e:
        print(f"    API error (org search): {e}")
        return [], 0


def search_people_at_org(org_id):
    """Find people with bar-relevant titles at an organization."""
    payload = {
        "api_key": APOLLO_API_KEY,
        "organization_ids": [org_id],
        "person_titles": TARGET_TITLES,
        "page": 1,
        "per_page": 10,
    }
    try:
        resp = requests.post(f"{BASE_URL}/mixed_people/search", json=payload, headers=apollo_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json().get("people", [])
    except requests.RequestException as e:
        print(f"    API error (people search): {e}")
        return []


def run():
    if not APOLLO_API_KEY:
        print("ERROR: APOLLO_API_KEY not set in .env")
        return

    existing_emails, existing_orgs = load_existing_emails()
    print(f"\nApollo Discovery: finding new bar contacts")
    print(f"  Known emails: {len(existing_emails)}")
    print(f"  Known orgs: {len(existing_orgs)}")
    print(f"  Target: {TARGET_CONTACTS} new contacts\n")

    # Load existing discovery results and state
    discovered = []
    if DISCOVERY_FILE.exists():
        discovered = json.loads(DISCOVERY_FILE.read_text())
    discovered_emails = {(c.get("contact_email") or "").lower() for c in discovered}

    state = load_state()
    keyword_idx = state.get("keyword_index", 0)
    page = state.get("page", 1)
    total_found = len(discovered)

    while keyword_idx < len(SEARCH_KEYWORDS) and total_found < TARGET_CONTACTS:
        keyword = SEARCH_KEYWORDS[keyword_idx]
        print(f"--- Keyword: '{keyword}' (page {page}) ---")

        orgs, total_pages = search_orgs(keyword, page)
        time.sleep(RATE_LIMIT_DELAY)

        if not orgs:
            print(f"  No orgs found, moving to next keyword")
            keyword_idx += 1
            page = 1
            state.update({"keyword_index": keyword_idx, "page": page})
            save_state(state)
            continue

        for org in orgs:
            if total_found >= TARGET_CONTACTS:
                break

            org_name = org.get("name", "")
            org_id = org.get("id")
            if not org_id:
                continue

            # Skip known orgs
            if org_name.lower().strip() in existing_orgs:
                continue

            print(f"  Org: {org_name}")

            people = search_people_at_org(org_id)
            time.sleep(RATE_LIMIT_DELAY)

            for person in people:
                email = person.get("email")
                if not email:
                    continue
                if email.lower() in existing_emails or email.lower() in discovered_emails:
                    continue

                contact = {
                    "bar_name": org_name,
                    "city": person.get("city") or org.get("city") or "",
                    "website": org.get("website_url") or "",
                    "contact_name": person.get("name", ""),
                    "contact_title": person.get("title", ""),
                    "contact_email": email,
                    "instagram": "",
                    "bar_style": "",
                    "notable_for": "",
                    "pitch_angle": "",
                    "researched_at": datetime.utcnow().isoformat(),
                    "source": "apollo_discovery",
                    "apollo_email": email,
                    "apollo_confidence": person.get("email_confidence"),
                    "apollo_person_id": person.get("id"),
                    "apollo_enriched_at": datetime.utcnow().isoformat(),
                }
                discovered.append(contact)
                discovered_emails.add(email.lower())
                existing_emails.add(email.lower())
                total_found += 1
                print(f"    + {person.get('name')} ({person.get('title')}) — {email}")

            existing_orgs.add(org_name.lower().strip())

        # Next page or next keyword
        if page < total_pages:
            page += 1
        else:
            keyword_idx += 1
            page = 1

        state.update({"keyword_index": keyword_idx, "page": page, "total_found": total_found})
        save_state(state)

        # Save progress
        DISCOVERY_FILE.parent.mkdir(parents=True, exist_ok=True)
        DISCOVERY_FILE.write_text(json.dumps(discovered, indent=2))

    # Final save
    DISCOVERY_FILE.parent.mkdir(parents=True, exist_ok=True)
    DISCOVERY_FILE.write_text(json.dumps(discovered, indent=2))

    print(f"\n{'='*60}")
    print(f"Apollo Discovery Complete")
    print(f"  New contacts found: {total_found}")
    print(f"  Output: {DISCOVERY_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    run()
