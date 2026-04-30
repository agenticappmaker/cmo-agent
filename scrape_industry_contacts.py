#!/usr/bin/env python3
"""
Industry Contact Scraper for Spirit Library outreach.

Scrapes publicly available email addresses from:
1. Bar/restaurant websites (contact pages)
2. Cocktail blogs and media sites
3. Bartending schools and programs
4. Spirits brand press/partnership pages
5. Cocktail influencer bios (Instagram, YouTube, TikTok)
6. Professional bartender associations
7. Event/festival organizer pages

Deduplicates, validates format, and saves to CSV + JSON.
"""

import re
import json
import csv
import time
import subprocess
import urllib.parse
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent / "outreach" / "scraped_contacts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
SKIP_DOMAINS = {
    'example.com', 'test.com', 'email.com', 'domain.com', 'yoursite.com',
    'sentry.io', 'github.com', 'npmjs.com', 'googleapis.com', 'gstatic.com',
    'w3.org', 'schema.org', 'jquery.com', 'cloudflare.com', 'facebook.com',
    'twitter.com', 'instagram.com', 'tiktok.com', 'google.com', 'apple.com',
    'microsoft.com', 'amazonaws.com', 'gravatar.com', 'wordpress.org',
}
SEEN_EMAILS = set()


def fetch_page(url, timeout=15):
    """Fetch a URL via curl and return text content."""
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), "-A",
             "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
             url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


def extract_emails(html):
    """Extract valid email addresses from HTML content."""
    raw = EMAIL_REGEX.findall(html)
    valid = []
    for email in raw:
        email = email.lower().strip()
        domain = email.split('@')[1] if '@' in email else ''
        # Skip common non-contact emails
        if domain in SKIP_DOMAINS:
            continue
        if email in SEEN_EMAILS:
            continue
        if any(x in email for x in ['noreply', 'no-reply', 'mailer-daemon', 'postmaster', 'webmaster', 'abuse@']):
            continue
        if not re.match(r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$', email):
            continue
        # Skip image/file extensions
        if any(email.endswith(x) for x in ['.png', '.jpg', '.gif', '.svg', '.css', '.js']):
            continue
        SEEN_EMAILS.add(email)
        valid.append(email)
    return valid


def scrape_google_results(query, num_pages=3):
    """Scrape emails from Google search results pages."""
    emails_found = []
    for page in range(num_pages):
        start = page * 10
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&start={start}"
        html = fetch_page(search_url)

        # Extract URLs from Google results
        urls = re.findall(r'https?://[^\s"<>]+', html)
        # Filter to likely contact pages
        contact_urls = [u for u in urls if any(x in u.lower() for x in
            ['contact', 'about', 'team', 'press', 'partner', 'info@', 'hello@', 'mailto:'])]

        for url in contact_urls[:5]:
            if 'google.com' in url:
                continue
            page_html = fetch_page(url)
            found = extract_emails(page_html)
            for email in found:
                emails_found.append({"email": email, "source_url": url, "query": query})
            time.sleep(1)

        time.sleep(2)
    return emails_found


def scrape_direct_sites(urls_with_category):
    """Scrape specific known industry websites for contact emails."""
    results = []
    for url, category, name in urls_with_category:
        print(f"  Scraping {name}...", end=" ", flush=True)
        html = fetch_page(url)
        found = extract_emails(html)
        for email in found:
            results.append({
                "email": email,
                "name": name,
                "category": category,
                "source_url": url,
            })
        print(f"{len(found)} emails", flush=True)
        time.sleep(1.5)
    return results


# ─── Target Sites ─────────────────────────────────────────────────────────────

BAR_ASSOCIATION_SITES = [
    ("https://www.usbg.org/contact", "bar_association", "USBG"),
    ("https://talesofthecocktail.org/contact", "bar_association", "Tales of the Cocktail"),
    ("https://www.barschool.net/contact", "bartending_school", "European Bartender School"),
    ("https://www.nationalbartenderschools.com/contact", "bartending_school", "National Bartenders School"),
    ("https://www.abc-bartending.com/contact", "bartending_school", "ABC Bartending"),
    ("https://barsmarts.com", "bartending_school", "BarSmarts"),
]

COCKTAIL_MEDIA_SITES = [
    ("https://imbibemagazine.com/contact/", "media", "Imbibe Magazine"),
    ("https://imbibemagazine.com/about/", "media", "Imbibe About"),
    ("https://punchdrink.com/about/", "media", "Punch Drink"),
    ("https://www.liquor.com/about-us-5093998", "media", "Liquor.com"),
    ("https://vinepair.com/about/", "media", "VinePair"),
    ("https://www.diffordsguide.com/contact", "media", "Difford's Guide"),
    ("https://www.thespruceeats.com/about-us-4770925", "media", "The Spruce Eats"),
    ("https://www.seriouseats.com/about-us", "media", "Serious Eats"),
    ("https://food52.com/about", "media", "Food52"),
    ("https://www.saveur.com/about/", "media", "Saveur"),
    ("https://www.tastingtable.com/about/", "media", "Tasting Table"),
    ("https://www.bonappetit.com/contact-us", "media", "Bon Appetit"),
    ("https://www.eater.com/contact", "media", "Eater"),
    ("https://www.epicurious.com/contact", "media", "Epicurious"),
]

SPIRITS_BRAND_SITES = [
    ("https://www.hendricksgin.com/contact/", "spirits_brand", "Hendrick's Gin"),
    ("https://www.aviationgin.com/contact", "spirits_brand", "Aviation Gin"),
    ("https://www.stgermain.fr/en/contact", "spirits_brand", "St-Germain"),
    ("https://www.fever-tree.com/en_US/contact-us", "spirits_brand", "Fever-Tree"),
    ("https://www.qmixers.com/contact", "spirits_brand", "Q Mixers"),
    ("https://www.jackrudycocktailco.com/pages/contact", "spirits_brand", "Jack Rudy"),
    ("https://cocktailkingdom.com/pages/contact", "bar_tools", "Cocktail Kingdom"),
    ("https://www.angosturahouse.com/contact", "spirits_brand", "Angostura"),
    ("https://www.campari.com/contact", "spirits_brand", "Campari Group"),
    ("https://www.negroni.com/contact", "spirits_brand", "Negroni"),
]

BAR_DIRECTORIES = [
    ("https://www.yelp.com/search?find_desc=cocktail+bar&find_loc=New+York", "bar", "Yelp NYC Cocktail Bars"),
    ("https://www.yelp.com/search?find_desc=cocktail+bar&find_loc=Los+Angeles", "bar", "Yelp LA Cocktail Bars"),
    ("https://www.yelp.com/search?find_desc=cocktail+bar&find_loc=Chicago", "bar", "Yelp Chicago Cocktail Bars"),
    ("https://www.yelp.com/search?find_desc=cocktail+bar&find_loc=Miami", "bar", "Yelp Miami Cocktail Bars"),
    ("https://www.yelp.com/search?find_desc=cocktail+bar&find_loc=San+Francisco", "bar", "Yelp SF Cocktail Bars"),
]

INFLUENCER_PAGES = [
    ("https://www.youtube.com/@CocktailChemistry/about", "influencer", "Cocktail Chemistry"),
    ("https://www.youtube.com/@HowToDrink/about", "influencer", "How To Drink"),
    ("https://www.youtube.com/@StevetheBartender/about", "influencer", "Steve the Bartender"),
    ("https://www.youtube.com/@TipsyBartender/about", "influencer", "Tipsy Bartender"),
    ("https://www.youtube.com/@theEducatedBarfly/about", "influencer", "Educated Barfly"),
    ("https://www.youtube.com/@AndersErickson/about", "influencer", "Anders Erickson"),
]

GOOGLE_QUERIES = [
    '"contact us" cocktail bar email site:.com',
    '"partnerships" "cocktail" email site:.com',
    '"info@" cocktail bar manager',
    '"press@" spirits brand cocktail',
    '"hello@" craft cocktail bar',
    '"events@" cocktail bar',
    '"booking@" cocktail lounge',
    'bartender association contact email',
    'mixology school contact email',
    'cocktail competition organizer email',
    'spirits distributor partnership email',
    'cocktail catering company email',
    'mobile bar company email contact',
    'cocktail event planner email',
    'bar consulting company email contact',
    'cocktail subscription box contact email',
    'home bar supplies company email',
    'bitters company contact email',
    'cocktail garnish supplier email',
    'bar menu design company email',
]


def main():
    print("=" * 60)
    print("  SPIRIT LIBRARY — INDUSTRY CONTACT SCRAPER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    all_contacts = []

    # Phase 1: Direct industry sites
    print("\n📋 Phase 1: Scraping known industry sites...")
    all_sites = (
        BAR_ASSOCIATION_SITES + COCKTAIL_MEDIA_SITES +
        SPIRITS_BRAND_SITES + BAR_DIRECTORIES + INFLUENCER_PAGES
    )
    direct = scrape_direct_sites(all_sites)
    all_contacts.extend(direct)
    print(f"  → {len(direct)} emails from direct sites")

    # Phase 2: Google search scraping
    print("\n🔍 Phase 2: Google search scraping...")
    for i, query in enumerate(GOOGLE_QUERIES):
        print(f"  [{i+1}/{len(GOOGLE_QUERIES)}] {query[:50]}...", end=" ", flush=True)
        found = scrape_google_results(query, num_pages=2)
        all_contacts.extend(found)
        print(f"{len(found)} emails", flush=True)
        time.sleep(3)  # Be respectful of Google rate limits

    # Deduplicate
    seen = set()
    unique = []
    for c in all_contacts:
        if c["email"] not in seen:
            seen.add(c["email"])
            unique.append(c)

    print(f"\n{'─' * 50}")
    print(f"  Total unique emails: {len(unique)}")

    # Save JSON
    json_path = OUTPUT_DIR / "industry_contacts.json"
    with open(json_path, "w") as f:
        json.dump(unique, f, indent=2)

    # Save CSV
    csv_path = OUTPUT_DIR / "industry_contacts.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["email", "name", "category", "source_url"])
        for c in unique:
            writer.writerow([c["email"], c.get("name", ""), c.get("category", ""), c.get("source_url", "")])

    print(f"  Saved to: {json_path}")
    print(f"  Saved to: {csv_path}")

    # Category breakdown
    cats = {}
    for c in unique:
        cat = c.get("category", c.get("query", "unknown"))
        cats[cat] = cats.get(cat, 0) + 1
    print(f"\n  By category:")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")


if __name__ == "__main__":
    main()
