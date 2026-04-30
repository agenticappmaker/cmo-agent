#!/usr/bin/env python3
"""
UPC + Ingredients Database Scraper for EU Approved Project (SMO-55)
Uses OpenFoodFacts API to download US food/beverage products and flag
those containing EU-banned ingredients.

Usage: ~/spirit_venv/bin/python upc_scraper.py [--pages N] [--update-paperclip]
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://world.openfoodfacts.org"
SEARCH_URL = f"{BASE_URL}/api/v2/search"

OUTPUT_DIR = Path(__file__).parent / "scraped_data"
PRODUCTS_FILE = OUTPUT_DIR / "us_products.json"
FLAGGED_FILE = OUTPUT_DIR / "flagged_products.json"

# Categories most relevant to EU-banned ingredient checking
PRIORITY_CATEGORIES = [
    "snacks",
    "cereals-and-potatoes",
    "sugary-snacks",
    "beverages",
    "meals",
    "breads",
    "dairy",
    "candies",
    "sauces",
    "frozen-foods",
    "chips-and-fries",
    "cookies",
    "cakes",
    "sodas",
    "energy-drinks",
    "sports-drinks",
    "fruit-juices",
    "ice-creams",
    "chocolates",
    "processed-meats",
]

# EU-banned or restricted ingredients (patterns for regex matching)
EU_BANNED_INGREDIENTS = {
    "Red 40": r"(?i)\b(red\s*(?:#?\s*)?40|allura\s*red|FD&C\s*Red\s*(?:No\.?\s*)?40|E129)\b",
    "Yellow 5": r"(?i)\b(yellow\s*(?:#?\s*)?5|tartrazine|FD&C\s*Yellow\s*(?:No\.?\s*)?5|E102)\b",
    "Yellow 6": r"(?i)\b(yellow\s*(?:#?\s*)?6|sunset\s*yellow|FD&C\s*Yellow\s*(?:No\.?\s*)?6|E110)\b",
    "Blue 1": r"(?i)\b(blue\s*(?:#?\s*)?1|brilliant\s*blue|FD&C\s*Blue\s*(?:No\.?\s*)?1|E133)\b",
    "Blue 2": r"(?i)\b(blue\s*(?:#?\s*)?2|indigo\s*carmine|FD&C\s*Blue\s*(?:No\.?\s*)?2|E132)\b",
    "Red 3": r"(?i)\b(red\s*(?:#?\s*)?3|erythrosine|FD&C\s*Red\s*(?:No\.?\s*)?3|E127)\b",
    "Green 3": r"(?i)\b(green\s*(?:#?\s*)?3|fast\s*green|FD&C\s*Green\s*(?:No\.?\s*)?3)\b",
    "BHA": r"(?i)\b(BHA|butylated\s*hydroxyanisole|E320)\b",
    "BHT": r"(?i)\b(BHT|butylated\s*hydroxytoluene|E321)\b",
    "Potassium bromate": r"(?i)\b(potassium\s*bromate|E924)\b",
    "Brominated vegetable oil": r"(?i)\b(brominated\s*vegetable\s*oil|BVO)\b",
    "Azodicarbonamide": r"(?i)\b(azodicarbonamide|ADA|E927a)\b",
    "rBGH/rBST": r"(?i)\b(rBGH|rBST|recombinant\s*bovine\s*(growth\s*hormone|somatotropin))\b",
    "Titanium dioxide": r"(?i)\b(titanium\s*dioxide|TiO2|E171)\b",
    "Propylparaben": r"(?i)\b(propylparaben|E217)\b",
    "TBHQ": r"(?i)\b(TBHQ|tert.butylhydroquinone|tertiary\s*butylhydroquinone)\b",
    "Artificial colors (general)": r"(?i)\b(artificial\s*colou?r|synthetic\s*colou?r)\b",
}

DEFAULT_PAGES = 5  # pages per category (50 products/page)

# Resend email config
def _load_env_from_dotenv() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

_load_env_from_dotenv()

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
NOTIFY_EMAIL = "claudesonnet111@gmail.com"

# Paperclip config
PAPERCLIP_BASE = "http://127.0.0.1:3100/api"
PAPERCLIP_COMPANY_ID = "c65ddc6b-cab6-4d06-aed1-4a23b58c82e8"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_get(url, retries=3, delay=1.0):
    """GET JSON from a URL with retries."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "SmoreLabs-UPC-Scraper/1.0 (claudesonnet111@gmail.com)"
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            print(f"  [retry {attempt+1}/{retries}] {e}")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    return None


def load_existing_products():
    """Load existing products file, return dict keyed by barcode."""
    if PRODUCTS_FILE.exists():
        try:
            with open(PRODUCTS_FILE, "r") as f:
                data = json.load(f)
            return {p["barcode"]: p for p in data if p.get("barcode")}
        except (json.JSONDecodeError, KeyError):
            return {}
    return {}


def save_products(products_dict):
    """Save products dict to JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(list(products_dict.values()), f, indent=2, ensure_ascii=False)


def extract_product(raw):
    """Extract relevant fields from an OpenFoodFacts product dict."""
    code = raw.get("code", "")
    if not code:
        return None
    return {
        "barcode": code,
        "product_name": raw.get("product_name", ""),
        "brand": raw.get("brands", ""),
        "ingredients_text": raw.get("ingredients_text", ""),
        "categories": raw.get("categories", ""),
        "nutrition_grade": raw.get("nutrition_grades", raw.get("nutrition_grade_fr", "")),
        "countries": raw.get("countries", ""),
        "image_url": raw.get("image_front_small_url", ""),
    }


def check_banned_ingredients(product):
    """Return list of EU-banned ingredients found in a product."""
    text = product.get("ingredients_text", "") or ""
    if not text:
        return []
    found = []
    for name, pattern in EU_BANNED_INGREDIENTS.items():
        if re.search(pattern, text):
            found.append(name)
    return found


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def scrape_category(category, pages, products_dict):
    """Scrape one OFF category for US products, return count of new products."""
    new_count = 0
    for page in range(1, pages + 1):
        params = urllib.parse.urlencode({
            "categories_tags_en": category,
            "countries_tags_en": "united-states",
            "fields": "code,product_name,brands,ingredients_text,categories,nutrition_grades,nutrition_grade_fr,countries,image_front_small_url",
            "page_size": 50,
            "page": page,
            "json": 1,
        })
        url = f"{SEARCH_URL}?{params}"
        data = api_get(url)
        if not data:
            print(f"  Failed to fetch {category} page {page}")
            break

        raw_products = data.get("products", [])
        if not raw_products:
            break

        for raw in raw_products:
            product = extract_product(raw)
            if product and product["barcode"] not in products_dict:
                products_dict[product["barcode"]] = product
                new_count += 1

        print(f"  {category} p{page}: {len(raw_products)} fetched, {new_count} new so far")

        # Be polite to the API
        time.sleep(0.5)

    return new_count


def flag_products(products_dict):
    """Check all products for EU-banned ingredients, return flagged list."""
    flagged = []
    for product in products_dict.values():
        banned = check_banned_ingredients(product)
        if banned:
            flagged.append({
                **product,
                "eu_banned_ingredients_found": banned,
            })
    return flagged


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def send_email_summary(total_products, flagged_count, flagged_top10):
    """Send summary email via Resend API."""
    top_lines = ""
    for p in flagged_top10:
        top_lines += f"- {p['product_name']} ({p['brand']}): {', '.join(p['eu_banned_ingredients_found'])}\n"

    body_html = f"""<h2>UPC Scraper Run Complete</h2>
<p><strong>Total US products scraped:</strong> {total_products}</p>
<p><strong>Products with EU-banned ingredients:</strong> {flagged_count}</p>
<h3>Top flagged products:</h3>
<pre>{top_lines or 'None found'}</pre>
<p>Full results saved to <code>scraped_data/flagged_products.json</code></p>
<p style="color:#888;">— Smore Labs / EU Approved Project (SMO-55)</p>"""

    payload = json.dumps({
        "from": "Smore Labs <onboarding@resend.dev>",
        "to": [NOTIFY_EMAIL],
        "subject": f"UPC Scraper: {flagged_count} products flagged with EU-banned ingredients",
        "html": body_html,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"Email sent: {result.get('id', 'ok')}")
    except Exception as e:
        print(f"Email send failed: {e}")


# ---------------------------------------------------------------------------
# Paperclip integration
# ---------------------------------------------------------------------------

def update_paperclip_issue():
    """Find SMO-55 and update its status to in_progress."""
    url = f"{PAPERCLIP_BASE}/companies/{PAPERCLIP_COMPANY_ID}/issues"
    data = api_get(url)
    if not data:
        print("Could not reach Paperclip API")
        return

    issues = data if isinstance(data, list) else data.get("results", data.get("issues", data.get("data", [])))
    issue_id = None
    for issue in issues:
        if issue.get("identifier") == "SMO-55":
            issue_id = issue["id"]
            break

    if not issue_id:
        print("SMO-55 not found in Paperclip")
        return

    print(f"Found SMO-55 with id: {issue_id}")
    payload = json.dumps({"status": "in_progress"}).encode("utf-8")
    req = urllib.request.Request(
        f"{PAPERCLIP_BASE}/issues/{issue_id}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"SMO-55 updated to in_progress (HTTP {resp.status})")
    except Exception as e:
        print(f"Failed to update SMO-55: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    pages = DEFAULT_PAGES
    do_paperclip = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--pages" and i + 1 < len(args):
            pages = int(args[i + 1])
            i += 2
        elif args[i] == "--update-paperclip":
            do_paperclip = True
            i += 1
        else:
            i += 1

    print(f"=== UPC Scraper for EU Approved Project ===")
    print(f"Pages per category: {pages}")
    print(f"Categories: {len(PRIORITY_CATEGORIES)}")
    print()

    # Load existing data (append mode with dedup)
    products = load_existing_products()
    print(f"Existing products loaded: {len(products)}")

    # Scrape each category
    total_new = 0
    for cat in PRIORITY_CATEGORIES:
        print(f"\n--- Scraping: {cat} ---")
        new = scrape_category(cat, pages, products)
        total_new += new
        # Save after each category for resilience
        save_products(products)

    print(f"\n=== Scraping complete ===")
    print(f"Total products: {len(products)} ({total_new} new)")

    # Flag products with EU-banned ingredients
    flagged = flag_products(products)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(FLAGGED_FILE, "w") as f:
        json.dump(flagged, f, indent=2, ensure_ascii=False)
    print(f"Flagged products (EU-banned ingredients): {len(flagged)}")
    print(f"Saved to: {FLAGGED_FILE}")

    # Show top hits
    if flagged:
        print("\nTop flagged products:")
        for p in flagged[:10]:
            print(f"  {p['product_name']} ({p['brand']}): {', '.join(p['eu_banned_ingredients_found'])}")

    # Send email summary
    print("\nSending email summary...")
    send_email_summary(len(products), len(flagged), flagged[:10])

    # Update Paperclip
    if do_paperclip:
        print("\nUpdating Paperclip SMO-55...")
        update_paperclip_issue()

    print("\nDone.")


if __name__ == "__main__":
    main()
