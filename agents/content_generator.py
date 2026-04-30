"""
Content Generator — uses Claude to autonomously decide what to post
and write captions, hashtags, and image generation prompts.
"""

import anthropic
import json
import os
import random
from datetime import datetime
from pathlib import Path


def load_brand(brand_slug: str) -> dict:
    base = Path(__file__).parent.parent / "brands" / brand_slug
    with open(base / "config.json") as f:
        config = json.load(f)
    with open(base / "knowledge.md") as f:
        knowledge = f.read()
    history = _load_history(brand_slug)
    return {"config": config, "knowledge": knowledge, "history": history}


def _load_history(brand_slug: str) -> list:
    path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_history.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def _save_to_history(brand_slug: str, post: dict):
    path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_history.json"
    history = _load_history(brand_slug)
    history.append(post)
    # Keep last 100 posts
    history = history[-100:]
    with open(path, "w") as f:
        json.dump(history, f, indent=2)


def _load_used_cocktails(brand_slug: str) -> set:
    """Load the full set of cocktail names ever posted — prevents any repeat."""
    path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_used_cocktails.json"
    if path.exists():
        with open(path) as f:
            return set(json.load(f))
    return set()


def _save_used_cocktail(brand_slug: str, cocktail_name: str):
    path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_used_cocktails.json"
    used = _load_used_cocktails(brand_slug)
    used.add(cocktail_name.lower().strip())
    with open(path, "w") as f:
        json.dump(sorted(used), f, indent=2)


def _get_next_post_type(brand_slug: str) -> str:
    """
    Alternates between 'recipe' and 'feature' posts.
    Morning post = recipe, Evening post = feature.
    Tracks state in a simple file.
    """
    path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_post_type_state.json"
    if path.exists():
        with open(path) as f:
            state = json.load(f)
        # Alternate from last type
        next_type = "feature" if state.get("last_type") == "recipe" else "recipe"
    else:
        next_type = "recipe"  # Always start with a recipe

    with open(path, "w") as f:
        json.dump({"last_type": next_type, "updated_at": datetime.utcnow().isoformat()}, f)

    return next_type


SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "posts", "images", "spirit-library", "screenshots")

APP_FEATURES_FOR_POSTS = [
    {
        "name": "My Bar — Ingredient Search",
        "description": "Add what's in your home bar and instantly see every cocktail you can make. Search by spirit, mixer, or bitters.",
        "screenshot": "my-bar-search.png"
    },
    {
        "name": "Flavor Search",
        "description": "Filter 1,700+ cocktails by flavor: Smoky, Citrus, Bitter, Floral, Tropical, Creamy, Spicy, and more.",
        "screenshot": "library-grid.png"
    },
    {
        "name": "Create Your Own Cocktail",
        "description": "Build a custom recipe from scratch — pick your spirit, add ingredients with autocomplete, write steps, tag flavors and occasions. Save it with your name on it.",
        "screenshot": "create-cocktail.png"
    },
    {
        "name": "Share Menus",
        "description": "Curate a list of cocktails for a dinner party, date night, or bar menu — then share the whole thing via text or link.",
        "screenshot": "my-menus.png"
    },
    {
        "name": "Occasions Filter",
        "description": "Find the perfect drink for any moment — Date Night, Brunch, After Dinner, Happy Hour, Summer, Winter, Celebration.",
        "screenshot": "library-grid.png"
    },
    {
        "name": "Shopping List",
        "description": "Add ingredients from any recipe to your shopping list with one tap. Check them off as you shop.",
        "screenshot": "shopping-list.png"
    },
    {
        "name": "Substitutions Tab",
        "description": "Never get stuck without an ingredient. 140+ substitution suggestions across 25 categories — swap what you don't have.",
        "screenshot": "substitutions.png"
    },
    {
        "name": "Allergies & Avoidances",
        "description": "Set your allergies once and Spirit Library hides every recipe containing those ingredients. Safe drinking for everyone.",
        "screenshot": "allergies-filter.png"
    },
    {
        "name": "Save & Collect",
        "description": "Heart the cocktails you love, organize them into named collections, and access your favorites instantly.",
        "screenshot": "saved-collection.png"
    },
]


def generate_post(brand_slug: str, platform: str = "instagram", post_type: str = None) -> dict:
    """
    Autonomously generate a complete post for the given brand and platform.
    post_type: 'recipe' or 'feature'. If None, auto-alternates.
    Returns: { caption, hashtags, image_prompt, post_idea, pillar, post_type }
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    brand = load_brand(brand_slug)
    config = brand["config"]
    knowledge = brand["knowledge"]
    history = brand["history"]

    # Auto-alternate if not specified
    if post_type is None:
        post_type = _get_next_post_type(brand_slug)

    # Full list of ALL cocktails ever posted — zero repeats allowed
    used_cocktails = _load_used_cocktails(brand_slug)
    used_list = "\n".join(sorted(used_cocktails)) if used_cocktails else "none yet"

    # Also build recent post_idea list for additional context
    recent_ideas = ""
    if history:
        recent_ideas = "\n".join([
            f"- {p.get('post_idea', '')[:80]}"
            for p in history[-20:]
        ])

    # Pick random hashtags from pool + all core
    pool = config.get("hashtags_pool", [])
    core = config.get("hashtags_core", [])
    selected_pool = random.sample(pool, min(7, len(pool)))
    all_tags = core + selected_pool

    platform_guidance = {
        "instagram": "Instagram: caption 150-280 chars, engaging, 1-2 emojis ok. Hashtags appended separately.",
        "facebook":  "Facebook: conversational, 100-230 chars. Friendly tone, 1 emoji max.",
        "linkedin":  "LinkedIn: professional but warm, 150-280 chars.",
        "twitter":   "X/Twitter: punchy, max 200 chars. Hook immediately.",
        "tiktok":    "TikTok: 100-140 chars, energetic hook.",
    }.get(platform, "")

    CTA = "\n\nComment below your favorite recipes!\n\nSave and share entire menus with Spirit Library in the App Store!!!"

    if post_type == "recipe":
        prompt = f"""You are the autonomous CMO agent for {config['brand_name']}.

BRAND KNOWLEDGE:
{knowledge}

BRAND TONE: {config['tone']}
TARGET AUDIENCE: {config['target_audience']}
PLATFORM: {platform}
{platform_guidance}

YOUR TASK: Write a COCKTAIL RECIPE spotlight post.

COCKTAILS ALREADY POSTED — DO NOT USE ANY OF THESE:
{used_list}

Recent post ideas (for context):
{recent_ideas}

Rules:
1. Pick a SPECIFIC, NAMED cocktail NOT in the used list above. Be creative — go beyond the obvious classics. Consider: Naked & Famous, Oaxacan Old Fashioned, Toronto, Bijou, Bees Knees, Corpse Reviver #2, Clover Club, Trinidad Sour, Saturn, Fog Cutter, Chartreuse Swizzle, Mezcal Negroni, etc.
2. Write the caption — name the cocktail, describe the flavors, make it sound irresistible
3. IMPORTANT: The caption must NOT include a CTA (it will be appended)
4. Write a cinematic DALL-E image prompt for this specific cocktail

Respond ONLY as JSON:
{{
  "post_type": "recipe",
  "cocktail_name": "exact cocktail name",
  "post_idea": "one sentence describing the post concept",
  "pillar": "cocktail recipes and techniques",
  "caption": "the full caption text (no hashtags, no CTA)",
  "image_prompt": "detailed DALL-E prompt — cinematic lighting, the specific glass and garnish for this cocktail, rich colors",
  "reasoning": "why you chose this cocktail"
}}"""

    else:  # feature post
        feature = random.choice(APP_FEATURES_FOR_POSTS)
        prompt = f"""You are the autonomous CMO agent for {config['brand_name']}.

BRAND KNOWLEDGE:
{knowledge}

BRAND TONE: {config['tone']}
TARGET AUDIENCE: {config['target_audience']}
PLATFORM: {platform}
{platform_guidance}

YOUR TASK: Write an APP FEATURE showcase post for this feature:

FEATURE: {feature['name']}
DESCRIPTION: {feature['description']}

Rules:
1. Lead with a relatable hook or scenario (e.g. "Ever open your fridge and wonder what cocktail you can actually make?")
2. Describe the feature in plain, exciting language — what it does, why it's useful
3. Make the user WANT to open the app right now
4. Keep it conversational and specific — avoid generic "download our app" energy
5. Do NOT include a CTA in the caption (it will be appended)

Respond ONLY as JSON:
{{
  "post_type": "feature",
  "feature_name": "{feature['name']}",
  "post_idea": "one sentence describing the post concept",
  "pillar": "app features and user stories",
  "caption": "the full caption text (no hashtags, no CTA)",
  "reasoning": "hook strategy used"
}}"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    content = message.content[0].text.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    content = content.strip()

    post_data = json.loads(content)
    post_data["caption"] = post_data["caption"].rstrip() + CTA
    post_data["hashtags"] = " ".join(all_tags)
    post_data["platform"] = platform
    post_data["brand"] = brand_slug
    post_data["post_type"] = post_type
    post_data["generated_at"] = datetime.utcnow().isoformat()

    # For feature posts, use the real screenshot instead of generating an image
    if post_type == "feature":
        screenshot_path = os.path.join(SCREENSHOT_DIR, feature["screenshot"])
        if os.path.exists(screenshot_path):
            post_data["screenshot_path"] = screenshot_path
            post_data["image_prompt"] = None  # signal to skip image generation

    # Track the cocktail name to prevent future repeats
    if post_type == "recipe" and post_data.get("cocktail_name"):
        _save_used_cocktail(brand_slug, post_data["cocktail_name"])

    _save_to_history(brand_slug, post_data)
    return post_data


def build_future_prompts(brand_slug: str, count: int = 7) -> list:
    """
    Autonomously plan a week of post ideas and save them for future use.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    brand = load_brand(brand_slug)
    config = brand["config"]
    knowledge = brand["knowledge"]
    history = brand["history"]

    recent = ""
    if history:
        recent_posts = history[-20:]
        recent = "\n".join([f"- {p.get('post_idea', '')}" for p in recent_posts])

    prompt = f"""You are the autonomous CMO agent for {config['brand_name']}.

BRAND KNOWLEDGE:
{knowledge}

BRAND TONE: {config['tone']}
CONTENT PILLARS: {', '.join(config['content_pillars'])}

Recent posts:
{recent}

Plan {count} unique, varied post ideas for the next {count} days.
Each idea should cover a different pillar and topic. Think strategically about
what builds brand awareness, drives app downloads, and engages the audience.

Respond as a JSON array of objects:
[
  {{
    "day": 1,
    "post_idea": "brief concept",
    "pillar": "content pillar",
    "platform": "instagram or tiktok",
    "hook": "the opening line or visual hook",
    "notes": "any specific guidance for when this is generated"
  }}
]"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )

    content = message.content[0].text.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    content = content.strip()

    plans = json.loads(content)

    # Save to a content calendar file
    path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_calendar.json"
    with open(path, "w") as f:
        json.dump(plans, f, indent=2)

    print(f"✓ Saved {len(plans)} post ideas to content calendar")
    return plans
