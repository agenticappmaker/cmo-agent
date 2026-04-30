#!/Users/claudecode/spirit_venv/bin/python
"""
Cocktail Scout Agent — Smore Labs
Scrapes cocktail recipes from public sources, deduplicates against Spirit Library,
formats as TypeScript-compatible objects, and emails a summary via Resend.
Runs daily at 6am via launchd.
"""

import json
import os
import re
import sys
import time
import logging
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from html.parser import HTMLParser
from difflib import SequenceMatcher

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "scraped_cocktails"
RECIPES_FILE = OUTPUT_DIR / "new_recipes.json"
SEEN_URLS_FILE = OUTPUT_DIR / "seen_urls.json"
SPIRIT_DATA_DIR = Path.home() / "Documents" / "spiritlibrary-mobile" / "data"
LOG_FILE = SCRIPT_DIR / "logs" / "cocktail_scraper.log"

# ── API Keys ───────────────────────────────────────────────────────────────────
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

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
NOTIFY_EMAIL = "claudesonnet111@gmail.com"

# ── Valid enums (must match Spirit Library types) ──────────────────────────────
VALID_SPIRITS = {
    "Bourbon", "Gin", "Rum", "Tequila", "Vodka", "Mezcal", "Brandy",
    "Whiskey", "Champagne", "Scotch", "Rye", "Pisco", "Absinthe",
    "Aperol", "Amaro", "Sake"
}
VALID_FLAVORS = {
    "Spirit-forward", "Citrus", "Sweet", "Bitter", "Herbal", "Smoky",
    "Tropical", "Creamy", "Spicy", "Floral", "Fruity", "Refreshing",
    "Rich", "Dry", "Effervescent"
}
VALID_OCCASIONS = {
    "Date Night", "Party", "After Dinner", "Brunch", "Summer", "Winter",
    "Celebration", "Relaxing", "Happy Hour"
}
VALID_DIFFICULTY = {"Easy", "Intermediate", "Advanced"}

# ── RSS Feeds ──────────────────────────────────────────────────────────────────
RSS_SOURCES = [
    {
        "name": "Imbibe Magazine",
        "url": "https://imbibemagazine.com/feed/",
        "type": "rss",
    },
    {
        "name": "Punch Drink",
        "url": "https://punchdrink.com/feed/",
        "type": "rss",
    },
    {
        "name": "Liquor.com",
        "url": "https://www.liquor.com/feeds/all",
        "type": "rss",
    },
]

WEB_SOURCES = [
    {
        "name": "Difford's Guide - New Cocktails",
        "url": "https://www.diffordsguide.com/cocktails/search?sort=date",
        "type": "web",
    },
    {
        "name": "Steve the Bartender",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC4yMJKGFECsbxByFxhKASzQ",
        "type": "youtube_rss",
    },
]

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("cocktail_scout")


# ── HTML stripping helper ──────────────────────────────────────────────────────
class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []

    def handle_data(self, d):
        self.result.append(d)

    def get_text(self):
        return "".join(self.result)


def strip_html(html_str: str) -> str:
    s = HTMLStripper()
    s.feed(html_str or "")
    return s.get_text().strip()


# ── Deduplication ──────────────────────────────────────────────────────────────
def normalize_name(name: str) -> str:
    """Normalize cocktail name for fuzzy matching."""
    name = name.lower().strip()
    name = re.sub(r"^the\s+", "", name)
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def load_existing_cocktails() -> set:
    """Extract all cocktail IDs and normalized names from Spirit Library data."""
    existing = set()
    if not SPIRIT_DATA_DIR.exists():
        log.warning("Spirit Library data dir not found: %s", SPIRIT_DATA_DIR)
        return existing

    for ts_file in SPIRIT_DATA_DIR.glob("*.ts"):
        try:
            content = ts_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Extract IDs
        for m in re.finditer(r'id:\s*"([^"]+)"', content):
            existing.add(m.group(1).lower())

        # Extract names and normalize
        for m in re.finditer(r'name:\s*"([^"]+)"', content):
            existing.add(normalize_name(m.group(1)))

    log.info("Loaded %d existing cocktail IDs/names for dedup", len(existing))
    return existing


def is_duplicate(name: str, existing: set) -> bool:
    """Check if a cocktail name is a duplicate (exact or fuzzy)."""
    norm = normalize_name(name)
    # Exact match on normalized name
    if norm in existing:
        return True
    # Kebab-case ID match
    kebab = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")
    if kebab in existing:
        return True
    # Fuzzy match (>= 0.85 similarity)
    for ex in existing:
        if SequenceMatcher(None, norm, ex).ratio() >= 0.85:
            return True
    return False


# ── Seen URLs ──────────────────────────────────────────────────────────────────
def load_seen_urls() -> set:
    if SEEN_URLS_FILE.exists():
        try:
            return set(json.loads(SEEN_URLS_FILE.read_text()))
        except Exception:
            pass
    return set()


def save_seen_urls(urls: set):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_URLS_FILE.write_text(json.dumps(sorted(urls), indent=2))


# ── HTTP helpers ───────────────────────────────────────────────────────────────
def fetch_url(url: str, timeout: int = 30) -> str | None:
    """Fetch URL content with error handling."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "SmoreLabs-CocktailScout/1.0 (research bot; contact@smorelabs.com)"
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log.warning("Failed to fetch %s: %s", url, e)
        return None


# ── Claude Haiku for recipe parsing ───────────────────────────────────────────
def parse_recipe_with_haiku(title: str, raw_text: str) -> dict | None:
    """Use Claude Haiku to extract structured recipe data from messy HTML/text."""
    prompt = f"""Extract the cocktail recipe from this text. Return ONLY valid JSON (no markdown fences).

Title: {title}

Text:
{raw_text[:4000]}

Return JSON with these exact fields:
{{
  "name": "Display Name",
  "spirit": one of {json.dumps(sorted(VALID_SPIRITS))},
  "ingredients": [{{"item": "ingredient name", "amount": "2 oz"}}],
  "instructions": ["step 1", "step 2"],
  "glassware": "Rocks Glass" or "Coupe" or "Highball" or "Martini Glass" or "Collins Glass" or "Nick & Nora" or "Tiki Mug" or "Copper Mug" or "Flute" or "Wine Glass" or "Hurricane Glass" or "Shot Glass",
  "garnish": "description",
  "flavorTags": subset of {json.dumps(sorted(VALID_FLAVORS))},
  "occasionTags": subset of {json.dumps(sorted(VALID_OCCASIONS))},
  "difficulty": "Easy" or "Intermediate" or "Advanced",
  "description": "One sentence description of the cocktail.",
  "category": "Classic" or "Modern",
  "abv": "High" or "Medium" or "Low",
  "prepTime": "3 min" or "5 min" or "7 min"
}}

If this is NOT a cocktail recipe, return {{"skip": true}}.
Only include spirits from the valid list. If the primary spirit doesn't match, pick the closest."""

    payload = json.dumps({
        "model": "claude-haiku-4-20250414",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text = result["content"][0]["text"].strip()
            # Strip markdown fences if present
            text = re.sub(r"^```json?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            recipe = json.loads(text)
            if recipe.get("skip"):
                return None
            return recipe
    except Exception as e:
        log.warning("Haiku parsing failed for '%s': %s", title, e)
        return None


# ── Source scrapers ────────────────────────────────────────────────────────────
def scrape_rss(source: dict, seen_urls: set) -> list[tuple[str, str, str]]:
    """Parse RSS feed, return list of (title, url, description) for cocktail-related entries."""
    results = []
    xml_text = fetch_url(source["url"])
    if not xml_text:
        return results

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("RSS parse error for %s: %s", source["name"], e)
        return results

    # Handle both RSS 2.0 and Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)

    cocktail_keywords = re.compile(
        r"cocktail|recipe|drink|mix|spirit|bourbon|gin|rum|tequila|vodka|mezcal|whiskey|scotch|rye|martini|daiquiri|margarita|negroni|sour|fizz|julep|mule|spritz|punch|highball|old.fashioned",
        re.IGNORECASE,
    )

    for item in items[:30]:  # Limit per feed
        title_el = item.find("title") or item.find("atom:title", ns)
        link_el = item.find("link") or item.find("atom:link", ns)
        desc_el = item.find("description") or item.find("atom:summary", ns) or item.find("atom:content", ns)

        title = (title_el.text if title_el is not None and title_el.text else "").strip()
        if link_el is not None:
            link = link_el.text if link_el.text else link_el.get("href", "")
        else:
            link = ""
        desc = strip_html(desc_el.text if desc_el is not None and desc_el.text else "")

        link = link.strip()
        if not link or link in seen_urls:
            continue

        # Only process cocktail-related content
        combined = f"{title} {desc}"
        if not cocktail_keywords.search(combined):
            continue

        results.append((title, link, desc))

    log.info("Found %d cocktail candidates from %s", len(results), source["name"])
    return results


def scrape_youtube_rss(source: dict, seen_urls: set) -> list[tuple[str, str, str]]:
    """Parse YouTube channel RSS for cocktail videos."""
    results = []
    xml_text = fetch_url(source["url"])
    if not xml_text:
        return results

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return results

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "media": "http://search.yahoo.com/mrss/",
    }

    cocktail_keywords = re.compile(
        r"cocktail|recipe|how to make|drink", re.IGNORECASE
    )

    for entry in root.findall(".//atom:entry", ns)[:20]:
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        desc_el = entry.find("media:group/media:description", ns)

        title = (title_el.text if title_el is not None else "").strip()
        link = link_el.get("href", "") if link_el is not None else ""
        desc = (desc_el.text if desc_el is not None else "").strip()

        if not link or link in seen_urls:
            continue
        if not cocktail_keywords.search(f"{title} {desc}"):
            continue

        results.append((title, link, desc))

    log.info("Found %d cocktail candidates from %s", len(results), source["name"])
    return results


def scrape_web_page(source: dict, seen_urls: set) -> list[tuple[str, str, str]]:
    """Scrape Difford's Guide or similar cocktail listing page."""
    results = []
    html = fetch_url(source["url"])
    if not html:
        return results

    # Extract cocktail links and names from the page
    # Difford's format: <a href="/cocktails/recipe/XXXX/name">Name</a>
    pattern = re.compile(
        r'href="(/cocktails/recipe/\d+/[^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE
    )

    base_url = "https://www.diffordsguide.com"
    for match in pattern.finditer(html)[:20]:
        path, name = match.group(1), match.group(2).strip()
        full_url = base_url + path
        if full_url in seen_urls:
            continue
        results.append((name, full_url, ""))

    log.info("Found %d cocktail candidates from %s", len(results), source["name"])
    return results


# ── Recipe processing ──────────────────────────────────────────────────────────
def make_id(name: str) -> str:
    """Convert name to kebab-case ID."""
    name = name.lower().strip()
    name = re.sub(r"^the\s+", "", name)
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def fetch_and_parse_recipe(title: str, url: str, desc: str) -> dict | None:
    """Fetch full page content and parse recipe with Haiku."""
    # If we have a good description, try that first
    text = desc
    if len(desc) < 200 and url:
        page = fetch_url(url)
        if page:
            text = strip_html(page)[:6000]

    if not text or len(text) < 50:
        return None

    recipe = parse_recipe_with_haiku(title, text)
    if not recipe:
        return None

    # Validate and fix fields
    name = recipe.get("name", title).strip()
    if not name:
        return None

    spirit = recipe.get("spirit", "")
    if spirit not in VALID_SPIRITS:
        return None  # Skip non-spirit cocktails

    cocktail_id = make_id(name)

    # Validate ingredients
    ingredients = recipe.get("ingredients", [])
    if not ingredients or not isinstance(ingredients, list):
        return None
    clean_ingredients = []
    for ing in ingredients:
        if isinstance(ing, dict) and "item" in ing and "amount" in ing:
            clean_ingredients.append({"item": str(ing["item"]), "amount": str(ing["amount"])})
    if not clean_ingredients:
        return None

    # Validate instructions
    instructions = recipe.get("instructions", [])
    if not instructions or not isinstance(instructions, list):
        return None

    # Clean flavor and occasion tags
    flavor_tags = [f for f in recipe.get("flavorTags", []) if f in VALID_FLAVORS]
    occasion_tags = [o for o in recipe.get("occasionTags", []) if o in VALID_OCCASIONS]
    difficulty = recipe.get("difficulty", "Intermediate")
    if difficulty not in VALID_DIFFICULTY:
        difficulty = "Intermediate"

    category = recipe.get("category", "Modern")
    if category not in ("Classic", "Modern"):
        category = "Modern"

    abv = recipe.get("abv", "Medium")
    if abv not in ("High", "Medium", "Low"):
        abv = "Medium"

    return {
        "id": cocktail_id,
        "name": name,
        "description": recipe.get("description", f"A delicious {name} cocktail."),
        "spirit": spirit,
        "difficulty": difficulty,
        "glassware": recipe.get("glassware", "Rocks Glass"),
        "garnish": recipe.get("garnish", "None"),
        "ingredients": clean_ingredients,
        "instructions": [str(s) for s in instructions],
        "flavorTags": flavor_tags or ["Spirit-forward"],
        "occasionTags": occasion_tags or ["Happy Hour"],
        "category": category,
        "abv": abv,
        "prepTime": recipe.get("prepTime", "5 min"),
        "color": "from-slate-800 to-slate-600",  # Default; can be customized later
        "sourceUrl": url,
        "scrapedAt": datetime.now(timezone.utc).isoformat(),
    }


# ── Email notification ─────────────────────────────────────────────────────────
def send_email_summary(new_recipes: list[dict]):
    """Send summary email via Resend API."""
    if not new_recipes:
        return

    recipe_lines = []
    for r in new_recipes:
        recipe_lines.append(
            f"- <b>{r['name']}</b> ({r['spirit']}) — {r['description']}<br>"
            f"  <a href=\"{r.get('sourceUrl', '#')}\">Source</a>"
        )

    body_html = f"""
    <h2>Cocktail Scout Report — {datetime.now().strftime('%Y-%m-%d')}</h2>
    <p>Found <b>{len(new_recipes)}</b> new cocktail recipe(s) for Spirit Library:</p>
    <ul>{''.join(f'<li>{line}</li>' for line in recipe_lines)}</ul>
    <p>Recipes saved to <code>scraped_cocktails/new_recipes.json</code>.</p>
    <p style="color: #888;">— Cocktail Scout Agent, Smore Labs</p>
    """

    payload = json.dumps({
        "from": "Cocktail Scout <onboarding@resend.dev>",
        "to": [NOTIFY_EMAIL],
        "subject": f"[Spirit Library] {len(new_recipes)} new cocktail(s) found",
        "html": body_html,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {RESEND_API_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            log.info("Email sent: %s", result.get("id", "ok"))
    except Exception as e:
        log.warning("Failed to send email: %s", e)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("Cocktail Scout starting — %s", datetime.now().isoformat())
    log.info("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load dedup data
    existing = load_existing_cocktails()
    seen_urls = load_seen_urls()

    # Load previously found recipes (to append, not overwrite)
    all_recipes = []
    if RECIPES_FILE.exists():
        try:
            all_recipes = json.loads(RECIPES_FILE.read_text())
        except Exception:
            all_recipes = []

    # Also add previously scraped recipe IDs/names to dedup set
    for r in all_recipes:
        existing.add(r.get("id", "").lower())
        existing.add(normalize_name(r.get("name", "")))

    new_recipes = []
    candidates = []

    # 1. Scrape RSS feeds
    for source in RSS_SOURCES:
        try:
            candidates.extend(scrape_rss(source, seen_urls))
        except Exception as e:
            log.error("Error scraping %s: %s", source["name"], e)

    # 2. Scrape YouTube RSS
    for source in WEB_SOURCES:
        try:
            if source["type"] == "youtube_rss":
                candidates.extend(scrape_youtube_rss(source, seen_urls))
            elif source["type"] == "web":
                candidates.extend(scrape_web_page(source, seen_urls))
        except Exception as e:
            log.error("Error scraping %s: %s", source["name"], e)

    log.info("Total candidates to process: %d", len(candidates))

    # 3. Process each candidate
    for title, url, desc in candidates:
        # Mark URL as seen regardless of outcome
        seen_urls.add(url)

        # Quick name dedup before expensive API call
        if is_duplicate(title, existing):
            log.info("SKIP (duplicate): %s", title)
            continue

        # Rate limit: be polite
        time.sleep(1)

        recipe = fetch_and_parse_recipe(title, url, desc)
        if not recipe:
            log.info("SKIP (no recipe extracted): %s", title)
            continue

        # Final dedup check on parsed name
        if is_duplicate(recipe["name"], existing):
            log.info("SKIP (duplicate after parse): %s", recipe["name"])
            continue

        # Add to results
        new_recipes.append(recipe)
        existing.add(recipe["id"])
        existing.add(normalize_name(recipe["name"]))
        log.info("NEW: %s (%s) — %s", recipe["name"], recipe["spirit"], recipe["id"])

    # 4. Save results
    all_recipes.extend(new_recipes)
    RECIPES_FILE.write_text(json.dumps(all_recipes, indent=2))
    save_seen_urls(seen_urls)

    log.info("Run complete: %d new recipes found, %d total stored", len(new_recipes), len(all_recipes))

    # 5. Email summary
    if new_recipes:
        send_email_summary(new_recipes)

    return new_recipes


if __name__ == "__main__":
    main()
