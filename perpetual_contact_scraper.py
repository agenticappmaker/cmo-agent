#!/usr/bin/env python3
"""
Perpetual Contact Scraper — Runs daily, finds new cocktail/bar industry contacts.

Cycle:
1. Search Pexels/Google/Bing for cocktail bar websites in rotating cities
2. Visit each site's contact page and extract emails
3. Deduplicate against all previously found contacts
4. Auto-send partnership email to new finds
5. Sleep until tomorrow, rotate to next city batch

Runs via launchd daily at 7am (before the 9am post).
"""

import re
import json
import csv
import time
import subprocess
import urllib.parse
import smtplib
import os
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ─── Config ───────────────────────────────────────────────────────────────────
GMAIL_USER = "spiritlibraryapp@gmail.com"
GMAIL_PASS = "hviq yshz bvhz funv"
WEBSITE = "https://spiritlibrary.app"
APP_STORE = "https://apps.apple.com/us/app/spirit-library/id6761500950"

OUTPUT_DIR = Path(__file__).parent / "outreach" / "perpetual"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MASTER_CONTACTS = OUTPUT_DIR / "all_contacts.json"
DAILY_LOG = OUTPUT_DIR / "daily_log.csv"
STATE_FILE = OUTPUT_DIR / "scraper_state.json"

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
SKIP_DOMAINS = {
    'example.com', 'sentry.io', 'sentry-next.wixpress.com', 'wixpress.com',
    'github.com', 'googleapis.com', 'gstatic.com', 'w3.org', 'schema.org',
    'cloudflare.com', 'facebook.com', 'twitter.com', 'instagram.com',
    'tiktok.com', 'google.com', 'apple.com', 'microsoft.com', 'gravatar.com',
    'wordpress.org', 'jquery.com', 'bootstrapcdn.com', 'fontawesome.com',
    'amazonaws.com', 'cloudfront.net', 'herokuapp.com',
}
SKIP_PREFIXES = [
    'noreply', 'no-reply', 'mailer-daemon', 'postmaster', 'webmaster',
    'abuse@', 'support@', 'billing@', 'subscriptions@', 'unsubscribe',
]

# Cities to rotate through (3 per cycle, every hour)
CITIES = [
    "New York", "Los Angeles", "Chicago", "Miami", "San Francisco",
    "Austin", "Nashville", "Seattle", "Portland", "Denver",
    "Boston", "Atlanta", "Houston", "Dallas", "Phoenix",
    "Las Vegas", "New Orleans", "Minneapolis", "Philadelphia", "Washington DC",
    "San Diego", "Charlotte", "Detroit", "Pittsburgh", "Richmond",
    "Savannah", "Charleston", "Louisville", "Memphis", "Kansas City",
    "Brooklyn", "Oakland", "Honolulu", "Scottsdale", "Santa Monica",
    "West Hollywood", "Williamsburg", "Hoboken", "Jersey City", "Stamford",
    "Greenwich", "White Plains", "Yonkers", "Raleigh", "Durham",
    "Columbus", "Indianapolis", "Milwaukee", "St Louis", "Salt Lake City",
    "Tampa", "Orlando", "Jacksonville", "Cincinnati", "Cleveland",
    "Buffalo", "Rochester", "Syracuse", "Albany", "Providence",
    "Hartford", "New Haven", "Burlington", "Asheville", "Boise",
    "Madison", "Ann Arbor", "Tucson", "Albuquerque", "El Paso",
    "Omaha", "Des Moines", "Lexington", "Knoxville", "Birmingham",
    "Mobile", "Pensacola", "Chattanooga", "Little Rock", "Tulsa",
    "Oklahoma City", "Wichita", "Spokane", "Tacoma", "Eugene",
    "Sacramento", "Fresno", "Long Beach", "Pasadena", "Napa",
    "Sonoma", "Santa Barbara", "Palm Springs", "Key West", "Sarasota",
]

# Direct bar/restaurant website URLs to scrape (known cocktail spots)
DIRECT_TARGETS = [
    # NYC cocktail bars
    "https://www.attaboy.us", "https://www.katanakirbyny.com",
    "https://www.employees-only.com", "https://www.thedead rabbit.com",
    "https://www.sweetandvicious.com", "https://www.angelshare.nyc",
    "https://www.blacktailnyc.com", "https://www.existing.conditions",
    # LA cocktail bars
    "https://www.thevernola.com", "https://www.barmaredsea.com",
    "https://www.honeycut.com", "https://www.theeldensla.com",
    # Chicago
    "https://www.theaviary.com", "https://www.violethour.com",
    "https://www.lost-lake.com", "https://www.three-dots-and-a-dash.com",
    # Spirits companies
    "https://www.stgeorgespirits.com", "https://www.deathsdoorspirits.com",
    "https://www.catoctin-creek.com", "https://www.adk-distilling.com",
    "https://www.koval-distillery.com", "https://www.corsairdistillery.com",
    "https://www.balconesdistilling.com", "https://www.stranahan.com",
    "https://www.copperandkings.com", "https://www.fewspirits.com",
    "https://www.westlanddistillery.com", "https://www.sagamorewhiskey.com",
    "https://www.unclevals.com", "https://www.tommyrotter.com",
    "https://www.empiricspirits.co", "https://www.lonerider-spirits.com",
    # Syrup/mixer companies
    "https://www.liberandcompany.com", "https://www.bgreynolds.com",
    "https://www.smallhandfoods.com", "https://www.el-guapo.com",
    "https://www.bittermilk.com", "https://www.hella cocktail.co",
    "https://www.pratt-standard.com", "https://www.18-21bitters.com",
    "https://www.portlandsyrups.com", "https://www.royalroseorganics.com",
    # Cocktail media/blogs
    "https://www.alcademics.com", "https://www.cocktailwonk.com",
    "https://www.cocktaildetour.com", "https://www.kindredcocktails.com",
    "https://www.distiller.com", "https://www.drinkhacker.com",
    "https://www.supercall.com", "https://www.cocktailsafe.org",
    # Bar tools/supplies
    "https://www.cocktailkingdom.com", "https://www.barproducts.com",
    "https://www.umamimartny.com", "https://www.thewhiskyexchange.com",
    "https://www.craftybartending.com", "https://www.advancedmixology.com",
    # Cocktail events
    "https://www.bcrumani.com", "https://www.speed-rack.org",
    "https://www.nightclubandbar.com", "https://www.barbizarre.com",
]

# Search query templates
QUERY_TEMPLATES = [
    "{city} cocktail bar contact email",
    "{city} craft cocktail bar website",
    "{city} best bars cocktail lounge",
    "{city} mixology bar events",
    "{city} speakeasy bar contact",
    "cocktail bar {city} partnerships",
    "{city} bartender association",
    "{city} spirits distributor",
    "{city} cocktail catering",
    "{city} mobile bar service email",
]


def load_all_known_emails():
    """Load every email we've ever found or sent to."""
    known = set()
    # Master perpetual list
    if MASTER_CONTACTS.exists():
        for c in json.loads(MASTER_CONTACTS.read_text()):
            known.add(c["email"].lower())
    # All other contact files
    outreach_dir = Path(__file__).parent / "outreach"
    for jf in outreach_dir.rglob("*.json"):
        try:
            data = json.loads(jf.read_text())
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "email" in item:
                        known.add(item["email"].lower())
        except:
            pass
    # All CSV logs
    for cf in outreach_dir.rglob("*.csv"):
        try:
            with open(cf) as f:
                for row in csv.reader(f):
                    for cell in row:
                        if "@" in cell and "." in cell:
                            known.add(cell.lower().strip())
        except:
            pass
    return known


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"city_index": 0, "total_found": 0, "total_sent": 0, "last_run": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def fetch(url, timeout=10):
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), "-A",
             "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        # Wait, we need the URL
        r = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), "-A",
             "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
             url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        return r.stdout if r.returncode == 0 else ""
    except:
        return ""


def extract_emails(html):
    raw = EMAIL_REGEX.findall(html)
    valid = []
    for email in raw:
        email = email.lower().strip()
        domain = email.split("@")[1] if "@" in email else ""
        if domain in SKIP_DOMAINS:
            continue
        if any(email.startswith(p) for p in SKIP_PREFIXES):
            continue
        if any(email.endswith(x) for x in [".png", ".jpg", ".gif", ".svg", ".css", ".js", ".webp"]):
            continue
        if not re.match(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$", email):
            continue
        valid.append(email)
    return list(set(valid))


def extract_urls_from_search(html):
    """Pull URLs from Bing search results."""
    urls = re.findall(r'href="(https?://[^"]+)"', html)
    # Filter to likely bar/restaurant sites
    filtered = []
    for u in urls:
        if any(x in u.lower() for x in ["bing.com", "microsoft.com", "google.com", "yelp.com", "tripadvisor.com"]):
            continue
        if any(x in u.lower() for x in ["contact", "about", "team", "press"]):
            filtered.append(u)
            continue
        # Also include main domains (we'll check /contact later)
        if re.match(r"https?://[^/]+/?$", u):
            filtered.append(u)
    return filtered[:10]


def search_bing(query):
    """Use Bing search."""
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count=20"
    html = fetch(url)
    return extract_urls_from_search(html)


def get_bar_sites_from_directories(city):
    """Get bar websites from known directories instead of search engines."""
    sites = []
    city_slug = city.lower().replace(" ", "-")
    city_url = urllib.parse.quote(city)

    # Infatuation / Punch / Eater city guides often link to bar websites
    directory_urls = [
        f"https://www.theinfatuation.com/{city_slug}/guides/best-cocktail-bars-{city_slug}",
        f"https://www.timeout.com/{city_slug}/bars/best-cocktail-bars-in-{city_slug}",
        f"https://www.thrillist.com/drink/{city_slug}/best-cocktail-bars-in-{city_slug}",
    ]

    for dir_url in directory_urls:
        html = fetch(dir_url, timeout=12)
        if not html:
            continue
        # Extract outbound links to bar websites
        urls = re.findall(r'href="(https?://(?!.*(?:theinfatuation|timeout|thrillist|yelp|google|facebook|instagram|twitter))[^"]+)"', html)
        # Keep unique domains
        seen_domains = set()
        for u in urls:
            domain = re.match(r'https?://([^/]+)', u)
            if domain and domain.group(1) not in seen_domains:
                seen_domains.add(domain.group(1))
                sites.append(u)
        time.sleep(2)

    # Also try some known craft bar aggregators
    bar_list_urls = [
        f"https://craftspirits.com/cocktail-bars/?location={city_url}",
        f"https://www.diffordsguide.com/bars/{city_slug}",
    ]
    for url in bar_list_urls:
        html = fetch(url, timeout=10)
        urls = re.findall(r'href="(https?://(?!.*diffordsguide)[^"]+)"', html)
        sites.extend(urls[:10])
        time.sleep(1)

    return list(set(sites))[:20]  # Max 20 sites per city


def scrape_site_for_emails(base_url):
    """Try the site's main page and common contact page paths."""
    emails = []
    paths = ["", "/contact", "/contact-us", "/about", "/about-us", "/press", "/partnerships"]
    for path in paths:
        url = base_url.rstrip("/") + path
        html = fetch(url, timeout=8)
        found = extract_emails(html)
        emails.extend(found)
        if found:
            break  # Got emails, no need to try more paths
        time.sleep(0.5)
    return list(set(emails))


def send_partnership_email(email, source_name=""):
    """Send a partnership pitch email."""
    name = source_name or email.split("@")[0].replace(".", " ").title()

    body = f"""Hi {name} team,

I'm Steven Samori, founder of Spirit Library — a free cocktail app with 1,500+ recipes, smart ingredient matching, and a substitution guide. We just launched on the App Store.

I'd love to explore a partnership — whether that's featured content, cross-promotion, or something creative.

Check it out: {WEBSITE}

Open to a quick chat?

Best,
Steven Samori
Smore Labs
{WEBSITE}"""

    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_USER
        msg["To"] = email
        msg["Subject"] = f"Partnership — Spirit Library Cocktail App"
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"    ✗ Send failed: {e}")
        return False


def log_daily(email, name, source, status):
    with open(DAILY_LOG, "a", newline="") as f:
        csv.writer(f).writerow([datetime.now().isoformat(), email, name, source, status])


def main():
    print("=" * 60)
    print("  PERPETUAL CONTACT SCRAPER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    state = load_state()
    known_emails = load_all_known_emails()
    print(f"  Known emails (skip): {len(known_emails)}")

    # Pick 3 cities for today
    start_idx = state["city_index"]
    today_cities = []
    for i in range(3):
        city = CITIES[(start_idx + i) % len(CITIES)]
        today_cities.append(city)
    state["city_index"] = (start_idx + 3) % len(CITIES)

    print(f"  Today's cities: {', '.join(today_cities)}")

    new_contacts = []
    new_sent = 0

    for city in today_cities:
        print(f"\n  📍 {city}")

        # Method 1: Bar directory sites (Infatuation, TimeOut, Thrillist, Difford's)
        print(f"    Checking bar directories...")
        bar_sites = get_bar_sites_from_directories(city)
        print(f"    Found {len(bar_sites)} bar websites")

        # Method 2: Also try Bing as backup
        queries = random.sample(QUERY_TEMPLATES, min(2, len(QUERY_TEMPLATES)))
        for qt in queries:
            q = qt.format(city=city)
            bing_urls = search_bing(q)
            bar_sites.extend(bing_urls)
            time.sleep(2)

        bar_sites = list(set(bar_sites))[:25]  # Cap at 25 per city

        for url in bar_sites:
            emails = scrape_site_for_emails(url)
            for email in emails:
                if email.lower() in known_emails:
                    continue

                known_emails.add(email.lower())
                domain = url.split("/")[2].replace("www.", "").split(".")[0] if len(url.split("/")) > 2 else "Unknown"
                contact = {
                    "email": email,
                    "name": domain.title(),
                    "city": city,
                    "source_url": url,
                    "found_at": datetime.now().isoformat(),
                }
                new_contacts.append(contact)

                # Auto-send
                print(f"    ✉ New: {email} — sending...", end=" ", flush=True)
                sent = send_partnership_email(email, contact["name"])
                status = "sent" if sent else "send_failed"
                log_daily(email, contact["name"], url, status)
                if sent:
                    new_sent += 1
                    print("✓")
                else:
                    print("✗")
                time.sleep(45)

            time.sleep(1)

    # Phase 2: Direct target sites (10 per cycle)
    direct_remaining = [u for u in DIRECT_TARGETS if u not in (load_state().get("scraped_directs", []))]
    batch = direct_remaining[:10]
    if batch:
        print(f"\n  🎯 Scraping {len(batch)} direct targets...")
        scraped_directs = state.get("scraped_directs", [])
        for url in batch:
            try:
                emails = scrape_site_for_emails(url)
                domain = url.split("/")[2].replace("www.", "").split(".")[0].title()
                for email in emails:
                    if email.lower() in known_emails:
                        continue
                    known_emails.add(email.lower())
                    contact = {
                        "email": email,
                        "name": domain,
                        "city": "Direct",
                        "source_url": url,
                        "found_at": datetime.now().isoformat(),
                    }
                    new_contacts.append(contact)
                    print(f"    ✉ New: {email} — sending...", end=" ", flush=True)
                    sent = send_partnership_email(email, contact["name"])
                    if sent:
                        new_sent += 1
                        print("✓")
                    else:
                        print("✗")
                    log_daily(email, contact["name"], url, "sent" if sent else "failed")
                    time.sleep(45)
            except:
                pass
            scraped_directs.append(url)
            time.sleep(1)
        state["scraped_directs"] = scraped_directs

    # Save new contacts to master list
    master = []
    if MASTER_CONTACTS.exists():
        master = json.loads(MASTER_CONTACTS.read_text())
    master.extend(new_contacts)
    MASTER_CONTACTS.write_text(json.dumps(master, indent=2))

    state["total_found"] = state.get("total_found", 0) + len(new_contacts)
    state["total_sent"] = state.get("total_sent", 0) + new_sent
    state["last_run"] = datetime.now().isoformat()
    save_state(state)

    print(f"\n{'─' * 50}")
    print(f"  Today: {len(new_contacts)} new contacts, {new_sent} emails sent")
    print(f"  Lifetime: {state['total_found']} found, {state['total_sent']} sent")
    print(f"  Next cities: {CITIES[(state['city_index']) % len(CITIES)]}, {CITIES[(state['city_index']+1) % len(CITIES)]}, {CITIES[(state['city_index']+2) % len(CITIES)]}")


if __name__ == "__main__":
    main()
