"""
Outreach Researcher — uses Claude + web search to build a rich profile
for each outreach target. Caches results to avoid re-researching.
"""

import anthropic
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

OUTREACH_DIR = Path(__file__).parent.parent / "outreach"
CACHE_FILE = OUTREACH_DIR / "research_cache.json"

APP_FEATURES = """
Spirit Library iOS App — Key Features (for partnership pitching):
1. MY BAR — Users add what's in their home bar (spirits, mixers, bitters), then search/filter
   by INGREDIENT and FLAVOR PROFILE to find cocktails they can make RIGHT NOW
2. FLAVOR SEARCH — filter by: Spirit-forward, Citrus, Sweet, Bitter, Herbal, Smoky, Tropical,
   Creamy, Spicy, Floral, Fruity, Refreshing, Rich, Dry, Effervescent
3. CREATE YOUR OWN COCKTAIL — full recipe builder with spirit picker, ingredient autocomplete,
   step-by-step instructions, flavor/occasion tags. Save and share your own recipes.
4. SHARE MENUS — curate cocktail lists and share full menus with friends, guests, or customers
5. COCKTAIL OF THE DAY — daily featured cocktail spotlight (sponsorship opportunity)
6. SHOPPING CART (COMING SOON) — buy missing ingredients from a recipe via Instacart/DoorDash/Uber Eats
7. 1,700+ COCKTAIL RECIPES — spanning Bourbon, Gin, Rum, Tequila, Vodka, Mezcal, Brandy,
   Whiskey, Champagne, Scotch, Rye, Pisco, Absinthe, Aperol, Amaro, Sake
8. OCCASIONS — search by: Date Night, Party, After Dinner, Brunch, Summer, Winter, Celebration,
   Relaxing, Happy Hour
"""


def load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    OUTREACH_DIR.mkdir(exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def _extract_json(text: str) -> dict:
    """Extract JSON object from Claude response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return json.loads(match.group())
        raise


def research_target(target: dict) -> dict:
    """
    Research a single target using Claude + web_search_20250305.
    Returns a rich profile with a tailored partnership strategy.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    name = target.get("name", "")
    handle = target.get("handle", target.get("instagram_handle", ""))
    category = target.get("category", "")
    website = target.get("website", "")
    notes = target.get("notes", "")
    outreach_type = target.get("outreach_type", "email")

    prompt = f"""You are researching a potential partnership target for Spirit Library — a cocktail recipe iOS app.

{APP_FEATURES}

TARGET:
Name: {name}
Instagram/Handle: @{handle}
Category: {category}
Website: {website or 'unknown'}
Internal notes: {notes}

Please search the web to find SPECIFIC information about this target:
1. Their audience size and demographics (follower counts, who follows them)
2. What exactly they do / what they sell / what content they create
3. Recent brand partnerships or sponsorships they've announced
4. A contact email or partnership inquiry email (check their website, Instagram bio, Linktree)
5. Any recent campaigns or launches relevant to cocktails/spirits

Then write a tailored partnership strategy that:
- References something SPECIFIC and CURRENT about them (recent post, campaign, product launch)
- Connects a SPECIFIC Spirit Library feature to their work (not generic)
- States clearly what they would gain from this partnership
- Gives a concrete partnership idea (not vague)

Respond as a JSON object ONLY (no markdown, no preamble):
{{
  "name": "{name}",
  "handle": "{handle}",
  "category": "{category}",
  "audience_size": "e.g. '2.1M Instagram followers'",
  "what_they_do": "2-3 sentence description of their brand/content/business",
  "recent_activity": "specific recent thing they did — campaign, launch, collab",
  "recent_partnerships": ["brand they partnered with", "another brand"],
  "contact_email": "the best email to reach them (or null if not found)",
  "contact_info": "other contact info found (linktree, booking link, etc.)",
  "best_feature_to_pitch": "the ONE Spirit Library feature most relevant to them",
  "partnership_idea": "one concrete partnership idea (e.g. 'Sponsored Cocktail of the Day for 30 days featuring Hendrick's recipes')",
  "why_they_should_care": "one sentence on what they get out of this partnership",
  "outreach_type": "{outreach_type}",
  "researched_at": "{datetime.utcnow().isoformat()}"
}}"""

    # Use haiku for research — fastest, lowest token cost, fits within rate limits
    # These are all well-known brands/influencers; training knowledge is sufficient.
    RESEARCH_MODEL = "claude-haiku-4-5-20251001"

    response = client.messages.create(
        model=RESEARCH_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt + "\n\nUse your training knowledge about this brand/person."}]
    )
    result_text = response.content[0].text
    try:
        profile = _extract_json(result_text)
    except Exception:
        profile = {
            "name": name,
            "handle": handle,
            "category": category,
            "what_they_do": notes,
            "contact_email": target.get("contact_email"),
            "outreach_type": outreach_type,
            "researched_at": datetime.utcnow().isoformat(),
            "raw_response": result_text[:500]
        }

    # Preserve any pre-known contact email from targets file
    if not profile.get("contact_email") and target.get("contact_email"):
        profile["contact_email"] = target["contact_email"]

    profile["_source_file"] = target.get("_source_file", "")
    return profile


def research_all_targets(force_refresh: bool = False, category_filter: str = None):
    """
    Research all targets from the targets/ directory.
    Caches results. Use force_refresh=True to re-research all.
    Use category_filter to only research a specific category (e.g. 'delivery').
    """
    cache = load_cache()
    targets_dir = OUTREACH_DIR / "targets"

    all_targets = []
    for target_file in sorted(targets_dir.glob("*.json")):
        if category_filter and target_file.stem != category_filter:
            continue
        with open(target_file) as f:
            targets = json.load(f)
        for t in targets:
            t["_source_file"] = target_file.stem
            all_targets.append(t)

    print(f"\n🔍 Research queue: {len(all_targets)} targets")
    if category_filter:
        print(f"   Filter: {category_filter}")

    done = 0
    skipped = 0
    failed = 0

    for i, target in enumerate(all_targets, 1):
        cache_key = target.get("handle") or target.get("name") or f"target_{i}"

        if cache_key in cache and not force_refresh:
            print(f"  [{i}/{len(all_targets)}] ⏭  {cache_key} (cached)")
            skipped += 1
            continue

        print(f"  [{i}/{len(all_targets)}] 🔎 {cache_key}...")
        try:
            profile = research_target(target)
            cache[cache_key] = profile
            save_cache(cache)
            print(f"      ✓ {profile.get('audience_size', '')} | Hook: {profile.get('best_feature_to_pitch', '')[:60]}")
            done += 1
            # Small delay — haiku uses ~800-1k tokens per call, well within limits
            if i < len(all_targets):
                time.sleep(2)
        except Exception as e:
            print(f"      ✗ Error: {e}")
            cache[cache_key] = {
                **target,
                "error": str(e),
                "researched_at": datetime.utcnow().isoformat()
            }
            save_cache(cache)
            failed += 1

    print(f"\n✅ Research complete: {done} new, {skipped} cached, {failed} failed")
    return cache


def show_research_summary():
    """Print a summary of all researched targets."""
    cache = load_cache()
    if not cache:
        print("No research cached yet. Run: python main.py outreach research")
        return

    errors = [k for k, v in cache.items() if "error" in v]
    good = {k: v for k, v in cache.items() if "error" not in v}

    print(f"\n📊 Research Summary ({len(cache)} targets total)")
    print(f"   ✓ Successfully researched: {len(good)}")
    print(f"   ✗ Errors: {len(errors)}")

    # Group by category
    by_cat = {}
    for k, v in good.items():
        cat = v.get("category", "unknown")
        by_cat.setdefault(cat, []).append(v)

    for cat, targets in sorted(by_cat.items()):
        print(f"\n  {cat.upper()} ({len(targets)})")
        for t in targets:
            email = t.get("contact_email", "—")
            size = t.get("audience_size", "—")
            print(f"    @{t.get('handle', t.get('name', '?')):<30} {size:<25} email: {email}")
