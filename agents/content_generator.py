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

# Rotated into recipe/series image prompts so each post gets a distinct visual style.
IMAGE_STYLE_ROTATION = [
    "overhead flat lay on dark wet slate, moody dramatic top-down composition, cocktail centered",
    "side-angle hero shot against a blurred moody bar backdrop, bokeh golden bar lights, editorial",
    "action shot — bartender's hands mid-pour or garnishing, motion blur on the liquid, cinematic",
    "bright natural window light on a marble kitchen counter, airy and aspirational, crisp shadows",
    "vintage editorial style, warm amber tones, candlelit bar atmosphere, 35mm film look",
    "low-angle dramatic shot looking up through the glass, ice and liquid refracting the light",
    "lush garden or outdoor terrace setting, dappled natural light, botanical elements as props",
    "dark moody speakeasy aesthetic, single spotlight, smoke wisps, rich jewel tones",
]


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


CONTENT_SERIES = [
    {
        "name": "Technique Explorer",
        "prompt_hint": "Pick ONE specific bartending technique (Japanese Hard Shake, fat-washing, expressing citrus oils, dry shaking for foam, double-straining, stirring vs shaking, flaming an orange peel, muddling, building in the glass, the throwing technique). Explain the technique, when to use it, and name 2-3 cocktails that showcase it.",
        "image_hint": "dramatic close-up of hands performing the bartending technique in a moody dimly-lit bar — action shot, motion blur on liquid, cinematic lighting, no text anywhere",
    },
    {
        "name": "Trending Ingredients Spotlight",
        "prompt_hint": "Highlight ONE ingredient currently trending in cocktail culture (hibiscus, yuzu, coffee liqueur, oat milk, butterfly pea flower, smoked salt, aquafaba, amaro, mezcal, saline solution, orgeat, falernum). Explain why it's trending and name 2-3 cocktails featuring it.",
        "image_hint": "the featured trending ingredient beautifully arranged with cocktails incorporating it — editorial food photography, shallow depth of field, dramatic side lighting, no text anywhere",
    },
    {
        "name": "Spirit Provenance & Terroir",
        "prompt_hint": "Feature ONE spirit region and its unique character (Jalisco tequila, Islay scotch, Oaxacan mezcal, Martinique rhum agricole, Kentucky bourbon, London dry gin, Cognac brandy, Japanese whisky). Tell the origin story and name signature cocktails from that tradition.",
        "image_hint": "atmospheric landscape of the spirit region with a bottle and signature cocktail in foreground — earthy, cinematic, golden hour lighting, feels like a travel documentary still, no text anywhere",
    },
    {
        "name": "Bartender Spotlight",
        "prompt_hint": "Share an expert bartender tip or insight about a trending technique, ingredient, or approach to cocktails. Give a practical pro tip that home bartenders can use tonight. Name specific cocktails where this applies.",
        "image_hint": "professional bartender at work behind a beautiful bar — moody atmospheric lighting, cocktail being prepared in foreground, bokeh background with bottles, editorial portrait photography, no text anywhere",
    },
    {
        "name": "Seasonal & Limited Release",
        "prompt_hint": "Feature a SEASONAL ingredient currently in season right now (spring: rhubarb, strawberry, elderflower, mint; summer: watermelon, peach, basil; fall: apple, pear, cinnamon, fig; winter: blood orange, cranberry, ginger, pomegranate). Name 2-3 cocktails that showcase it at its peak.",
        "image_hint": "the seasonal ingredient arranged beautifully alongside cocktails incorporating it — bright natural light, farmers market energy, fresh and appetizing, editorial food photography, no text anywhere",
    },
    {
        "name": "What Can I Make Challenge",
        "prompt_hint": "Present 3-4 common home bar ingredients and challenge followers: how many cocktails can YOU make with just these? Then reveal 3-4 cocktails possible. Drives the My Bar feature.",
        "image_hint": "3-4 spirit bottles and mixers arranged on a clean bar top — overhead flat lay shot, minimalist styling, warm lighting, inviting and aspirational, no text anywhere",
    },
    {
        "name": "Cocktail History Deep Dive",
        "prompt_hint": "Tell the origin story of ONE classic cocktail — who invented it, where, when, why. Make it a compelling narrative. Choose something with a great story (Sazerac, Last Word, Aviation, Penicillin, Jungle Bird, Paper Plane, Corpse Reviver).",
        "image_hint": "the cocktail in vintage noir style — dramatic shadows, art deco bar setting, moody and atmospheric, feels like a period film still from the era of the cocktail's invention, no text anywhere",
    },
    {
        "name": "Interesting Bar Facts",
        "prompt_hint": "Share ONE surprising, little-known bar or cocktail fact that will make people say 'wait, really?' Examples: why we clink glasses, why bartenders use jiggers, what proof actually means, why ice matters more than you think, the world's oldest bar, why shaken and stirred taste different, what a dash of bitters actually is, why cocktails are called cocktails. Make it fun, specific, and end with a cocktail to try.",
        "image_hint": "dramatic moody close-up of a bar detail related to the fact — ice in a glass, bitters bottle, jigger, cocktail napkin, vintage bar sign — cinematic lighting, shallow depth of field, no text anywhere",
    },
]

# Infographic templates — list-style single posts (rendered locally, no AI image gen)
INFOGRAPHIC_TEMPLATES = [
    {
        "theme_id": "seasonal",
        "prompt_hint": "5 cocktails perfect for the current season — name + one-line flavor description each. Pick a seasonal angle (spring brunch, summer poolside, fall fireside, winter holiday).",
    },
    {
        "theme_id": "occasion",
        "prompt_hint": "5 cocktails for a specific occasion — date night, dinner party, brunch, after-dinner, holiday gathering. Each with a one-line reason it fits that moment.",
    },
    {
        "theme_id": "spirit_deep_dive",
        "prompt_hint": "Pick ONE spirit (gin, mezcal, rye, rum, tequila, bourbon). List 5 essential cocktails every fan should know, each with a one-line description of why it matters.",
    },
    {
        "theme_id": "skill_levels",
        "prompt_hint": "5 cocktails arranged from beginner to expert difficulty. For each, name the cocktail and one-line takeaway about technique or ingredient required.",
    },
    {
        "theme_id": "flavor_profile",
        "prompt_hint": "5 cocktails matching a specific flavor profile (smoky, citrus-forward, herbal, bitter, tropical, creamy). Each with a one-line flavor description.",
    },
    {
        "theme_id": "underrated",
        "prompt_hint": "5 underrated or forgotten cocktails that deserve a comeback. Each with a one-line hook on what makes it special.",
    },
    {
        "theme_id": "world_tour",
        "prompt_hint": "5 cocktails from 5 different countries or regions. Name the cocktail, the place, and a one-line connection between drink and origin.",
    },
    {
        "theme_id": "ingredient_swap",
        "prompt_hint": "5 essential ingredient substitutions every home bartender should know. Each item: 'X → Y' with a one-line note on when it works.",
    },
]


def _get_next_post_type(brand_slug: str) -> str:
    """
    Rotation cycle: 6 unique post slots covering the full CMO mix.
      0: recipe       — single cocktail beauty shot (AI image)
      1: feature      — app feature / lifestyle social post (AI image)
      2: infographic  — list-style single (designed locally, no AI image)
      3: recipe       — single cocktail beauty shot (AI image)
      4: series       — educational carousel (multi-slide)
      5: feature      — app feature / lifestyle social post (AI image)

    Two posts/day at 9am + 7pm → one full cycle every 3 days. Per week:
    ~5 cocktails, ~5 features, ~2 infographics, ~2 carousels — variety the
    user explicitly asked for: cocktails, social, infographs, carousels.

    Series rotates evenly through CONTENT_SERIES (no 2x weighting on bar_facts).
    """
    path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_post_type_state.json"
    if path.exists():
        with open(path) as f:
            state = json.load(f)
        rotating_series_idx = state.get("rotating_series_idx", 0)
        rotating_info_idx = state.get("rotating_info_idx", 0)
        cycle_pos = state.get("cycle_pos", 0)
    else:
        cycle_pos = 0
        rotating_series_idx = 0
        rotating_info_idx = 0

    cycle = ["recipe", "feature", "infographic", "recipe", "series", "feature"]
    next_type = cycle[cycle_pos % len(cycle)]
    cycle_pos = (cycle_pos + 1) % len(cycle)

    series_idx = rotating_series_idx
    info_idx = rotating_info_idx

    if next_type == "series":
        series_idx = rotating_series_idx
        rotating_series_idx = (rotating_series_idx + 1) % len(CONTENT_SERIES)
    elif next_type == "infographic":
        info_idx = rotating_info_idx
        rotating_info_idx = (rotating_info_idx + 1) % len(INFOGRAPHIC_TEMPLATES)

    with open(path, "w") as f:
        json.dump({
            "last_type": next_type,
            "series_idx": series_idx,
            "info_idx": info_idx,
            "rotating_series_idx": rotating_series_idx,
            "rotating_info_idx": rotating_info_idx,
            "cycle_pos": cycle_pos,
            "updated_at": datetime.utcnow().isoformat(),
        }, f)

    return next_type


APP_FEATURES_FOR_POSTS = [
    {
        "name": "My Bar — Ingredient Search",
        "description": "Add what's in your home bar and instantly see every cocktail you can make. Search by spirit, mixer, or bitters.",
        "visual": "a beautifully arranged home bar shelf with premium spirit bottles glowing in warm backlight — bourbon, gin, rum, tequila, Aperol, vermouth lined up on dark wood shelving, aspirational home interior lifestyle photography, no text anywhere"
    },
    {
        "name": "Flavor Search",
        "description": "Filter 1,700+ cocktails by flavor: Smoky, Citrus, Bitter, Floral, Tropical, Creamy, Spicy, and more.",
        "visual": "a dramatic flat lay of cocktail ingredients representing different flavor profiles: citrus fruits sliced open, dried chilies, fresh herbs, smoked wood chips, tropical fruits — dark marble surface, editorial food photography, rich colors, no text"
    },
    {
        "name": "Create Your Own Cocktail",
        "description": "Build a custom recipe from scratch — pick your spirit, add ingredients with autocomplete, write steps, tag flavors and occasions. Save it with your name on it.",
        "visual": "close-up of a bartender's hands precisely measuring spirits into a jigger, cocktail tools and fresh ingredients laid out on a dark bar top, craft and creativity, moody professional bar photography, no text"
    },
    {
        "name": "Share Menus",
        "description": "Curate a list of cocktails for a dinner party, date night, or bar menu — then share the whole thing via text or link.",
        "visual": "an elegant dinner party table set with multiple cocktails in beautiful glassware, candles, flowers, guests' hands reaching in, warm golden light, sophisticated entertaining lifestyle photography, no text"
    },
    {
        "name": "Occasions Filter",
        "description": "Find the perfect drink for any moment — Date Night, Brunch, After Dinner, Happy Hour, Summer, Winter, Celebration.",
        "visual": "a romantic candlelit table for two with two stunning cocktails — a Negroni and a champagne coupe — soft bokeh background, intimate date night atmosphere, professional lifestyle photography, no text"
    },
    {
        "name": "Shopping Cart",
        "description": "Coming soon: tap any recipe and order the missing ingredients directly via Instacart, DoorDash, or Uber Eats.",
        "visual": "a premium grocery delivery bag on a kitchen counter next to fresh citrus fruits, a bottle of spirits, and cocktail tools — bright modern kitchen, clean lifestyle photography, no text"
    },
    {
        "name": "Substitutions Tab",
        "description": "Never get stuck without an ingredient. 140+ substitution suggestions across 25 categories — swap what you don't have.",
        "visual": "a flat lay of ingredient alternatives side by side on a marble surface: lemon next to lime, honey next to simple syrup, different bitters bottles arranged together — editorial food styling, natural light, no text"
    },
    {
        "name": "Allergies Filter",
        "description": "Filter all 1,700+ cocktails by allergen — nuts, dairy, gluten, eggs, soy, citrus, shellfish. Everyone finds something safe.",
        "visual": "a warm inclusive gathering scene: diverse group of friends toasting with different cocktails at a beautifully set table, everyone smiling, golden evening light, lifestyle photography, no text"
    },
]


def generate_post(brand_slug: str, platform: str = "instagram", post_type: str = None, topic: str = None) -> dict:
    """
    Autonomously generate a complete post for the given brand and platform.
    post_type: 'recipe' or 'feature'. If None, auto-alternates.
    topic: optional free-text theme override injected into the generation prompt.
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
        image_style = random.choice(IMAGE_STYLE_ROTATION)
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

{f"⚠️ MANDATORY TOPIC: {topic}. You MUST pick a cocktail that directly fits this theme. Do not deviate." if topic else ""}

Rules:
1. Pick a SPECIFIC, NAMED cocktail NOT in the used list above. Be creative — go beyond the obvious classics. Consider: Naked & Famous, Oaxacan Old Fashioned, Toronto, Bijou, Bees Knees, Corpse Reviver #2, Clover Club, Trinidad Sour, Saturn, Fog Cutter, Chartreuse Swizzle, Mezcal Negroni, etc.
2. Write the caption — name the cocktail, describe the flavors, make it sound irresistible
3. IMPORTANT: The caption must NOT include a CTA (it will be appended)
4. Write a cinematic gpt-image-2 image prompt for this specific cocktail

Respond ONLY as JSON:
{{
  "post_type": "recipe",
  "cocktail_name": "exact cocktail name",
  "post_idea": "one sentence describing the post concept",
  "pillar": "cocktail recipes and techniques",
  "caption": "the full caption text (no hashtags, no CTA)",
  "image_prompt": "detailed gpt-image-2 photorealistic prompt — VISUAL STYLE: {image_style} — include the specific glass type, garnish, and colors for this exact cocktail, no text or writing anywhere in the image",
  "reasoning": "why you chose this cocktail"
}}"""

    elif post_type == "series":
        # Pick the current series from state
        state_path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_post_type_state.json"
        series_idx = 0
        if state_path.exists():
            with open(state_path) as f:
                series_idx = json.load(f).get("series_idx", 0)
        series = CONTENT_SERIES[series_idx % len(CONTENT_SERIES)]

        prompt = f"""You are the autonomous CMO agent for {config['brand_name']}.

BRAND KNOWLEDGE:
{knowledge}

BRAND TONE: {config['tone']}
TARGET AUDIENCE: {config['target_audience']}
PLATFORM: {platform}
{platform_guidance}

YOUR TASK: Write a post for the "{series['name']}" content series.

SPECIFIC DIRECTION: {series['prompt_hint']}

Recent post ideas (DO NOT repeat these):
{recent_ideas}

Rules:
1. Be specific and educational — name real cocktails, real techniques, real ingredients
2. Make followers LEARN something and want to try it tonight
3. Write in the brand voice — sophisticated but approachable
4. Do NOT include a CTA (it will be appended)
5. The image must be DIFFERENT from a standard cocktail beauty shot — follow the image hint closely

Respond ONLY as JSON:
{{
  "post_type": "series",
  "series_name": "{series['name']}",
  "post_idea": "one sentence describing the post concept",
  "pillar": "{series['name'].lower()}",
  "caption": "the full caption text (no hashtags, no CTA)",
  "image_prompt": "{series['image_hint']} — ADDITIONALLY: [add specific details about what's shown based on your caption content]",
  "title_slide_image_prompt": "a single cinematic marketing-grade image prompt tailored to the carousel's hero content — the one cocktail, technique, ingredient, or scene that best represents what this carousel teaches. Editorial photography, dramatic lighting, rich depth, visually striking enough to stop a scroll. NO text anywhere.",
  "reasoning": "why this specific topic within the series",
  "carousel_slides": [
    {{"type": "title", "title": "3-5 word punchy title", "subtitle": "max 8 words"}},
    {{"type": "content", "heading": "2-4 word heading", "body": "ONE short sentence, max 15 words. Like a billboard.", "number": 1}},
    {{"type": "content", "heading": "2-4 word heading", "body": "ONE short sentence, max 15 words. Punchy and memorable.", "number": 2}},
    {{"type": "bullets", "heading": "2-4 word heading", "bullets": ["max 5 words each", "keep them punchy", "like a list"]}},
    {{"type": "recipe", "cocktail_name": "Cocktail Name", "ingredients": ["2 oz Spirit", "1 oz Citrus", "0.75 oz Syrup"], "glass": "glass type", "garnish": "garnish"}}
  ]

CRITICAL SLIDE RULES:
- Title: MAX 5 words
- Subtitle: MAX 8 words
- Content body: MAX 15 words per slide. ONE sentence only. Think billboard, not paragraph.
- Bullet points: MAX 5 words each
- Headings: MAX 4 words
- These are Instagram slides — people swipe fast. Every word must earn its place.
}}"""

    elif post_type == "infographic":
        state_path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_post_type_state.json"
        info_idx = 0
        if state_path.exists():
            with open(state_path) as f:
                info_idx = json.load(f).get("info_idx", 0)
        template = INFOGRAPHIC_TEMPLATES[info_idx % len(INFOGRAPHIC_TEMPLATES)]

        prompt = f"""You are the autonomous CMO agent for {config['brand_name']}.

BRAND KNOWLEDGE:
{knowledge}

BRAND TONE: {config['tone']}
TARGET AUDIENCE: {config['target_audience']}
PLATFORM: {platform}
{platform_guidance}

YOUR TASK: Write an INFOGRAPHIC-STYLE list post.

SPECIFIC DIRECTION: {template['prompt_hint']}

Recent post ideas (DO NOT repeat these):
{recent_ideas}

COCKTAILS ALREADY FEATURED — try to avoid these:
{used_list}

Rules:
1. Pick a tight, clear theme — the infographic must read as ONE coherent list
2. Title: punchy, scannable, max 6 words. Subtitle optional, max 8 words
3. Provide EXACTLY 5 list items
4. Each item: name (max 4 words) + description (max 12 words, one short line)
5. Caption: hook readers, tease the list, NO CTA (it will be appended)

Respond ONLY as JSON:
{{
  "post_type": "infographic",
  "infographic_title": "punchy title, max 6 words",
  "infographic_subtitle": "optional subtitle max 8 words, or empty string",
  "infographic_items": [
    {{"name": "Item 1 name", "description": "one-line description, max 12 words"}},
    {{"name": "Item 2 name", "description": "one-line description, max 12 words"}},
    {{"name": "Item 3 name", "description": "one-line description, max 12 words"}},
    {{"name": "Item 4 name", "description": "one-line description, max 12 words"}},
    {{"name": "Item 5 name", "description": "one-line description, max 12 words"}}
  ],
  "post_idea": "one sentence describing the post concept",
  "pillar": "infographic — {template['theme_id']}",
  "caption": "hook caption that teases the list — no CTA, no hashtags",
  "image_prompt": "",
  "reasoning": "why this theme fits this audience right now"
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
  "image_prompt": "gpt-image-2 photorealistic lifestyle photo showing: {feature['visual']} — clean, modern, editorial style, warm lighting, no text or writing anywhere",
  "reasoning": "hook strategy used"
}}"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048 if post_type == "series" else 1024,
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

    # Track the cocktail name to prevent future repeats
    if post_type == "recipe" and post_data.get("cocktail_name"):
        _save_used_cocktail(brand_slug, post_data["cocktail_name"])

    _save_to_history(brand_slug, post_data)
    return post_data


def generate_carousel_content(post_data: dict) -> list:
    """
    Extract carousel slide data from a series post.
    If the AI included carousel_slides in the response, use those.
    Otherwise, auto-generate slides from the caption.
    Always appends a CTA slide at the end.
    """
    slides = post_data.get("carousel_slides", [])

    if not slides:
        # Auto-generate from caption
        caption = post_data.get("caption", "")
        title = post_data.get("post_idea", "Cocktail Knowledge")
        series = post_data.get("series_name", "")

        # Split caption into chunks for slides
        sentences = [s.strip() for s in caption.replace("\n\n", "\n").split("\n") if s.strip()]

        slides.append({"type": "title", "title": title, "subtitle": series})
        for i, chunk in enumerate(sentences[:4]):
            slides.append({"type": "content", "heading": f"Part {i+1}", "body": chunk, "number": i + 1})

    # Always end with CTA slide
    if not slides or slides[-1].get("type") != "cta":
        slides.append({"type": "cta"})

    return slides


def generate_screenshot_caption(brand_slug: str, image_path: str, platform: str = "instagram") -> dict:
    """
    Generate a caption for a user-provided screenshot (no image generation).
    Uses Claude's vision to analyze the screenshot and write a relevant caption.
    Returns: { caption, hashtags, post_idea, pillar, post_type }
    """
    import base64
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    brand = load_brand(brand_slug)
    config = brand["config"]
    knowledge = brand["knowledge"]
    history = brand["history"]

    recent_ideas = ""
    if history:
        recent_ideas = "\n".join([
            f"- {p.get('post_idea', '')[:80]}"
            for p in history[-20:]
        ])

    # Read and encode the screenshot
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    ext = Path(image_path).suffix.lower()
    media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext.lstrip("."), "image/png")

    pool = config.get("hashtags_pool", [])
    core = config.get("hashtags_core", [])
    selected_pool = random.sample(pool, min(7, len(pool)))
    all_tags = core + selected_pool

    platform_guidance = {
        "instagram": "Instagram: caption 150-280 chars, engaging, 1-2 emojis ok. Hashtags appended separately.",
        "facebook":  "Facebook: conversational, 100-230 chars. Friendly tone, 1 emoji max.",
    }.get(platform, "")

    CTA = "\n\nComment below your favorite recipes!\n\nSave and share entire menus with Spirit Library in the App Store!!!"

    prompt = f"""You are the autonomous CMO agent for {config['brand_name']}.

BRAND KNOWLEDGE:
{knowledge}

BRAND TONE: {config['tone']}
TARGET AUDIENCE: {config['target_audience']}
PLATFORM: {platform}
{platform_guidance}

YOUR TASK: Look at this app screenshot and write a compelling social media caption for it.

Recent post ideas (avoid repetition):
{recent_ideas}

Rules:
1. Analyze the screenshot — what feature or screen is shown?
2. Write a caption that highlights what's shown, makes it exciting, and makes users want to download the app
3. Lead with a relatable hook or scenario
4. Keep it conversational and specific — avoid generic "download our app" energy
5. Do NOT include a CTA in the caption (it will be appended)

Respond ONLY as JSON:
{{
  "post_type": "screenshot",
  "post_idea": "one sentence describing what's shown in the screenshot",
  "pillar": "app features and user stories",
  "caption": "the full caption text (no hashtags, no CTA)",
  "reasoning": "what you see in the screenshot and your hook strategy"
}}"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
            {"type": "text", "text": prompt}
        ]}]
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
    post_data["post_type"] = "screenshot"
    post_data["image_path"] = str(image_path)
    post_data["generated_at"] = datetime.utcnow().isoformat()

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

    # Strip trailing incomplete content to get valid JSON
    try:
        plans = json.loads(content)
    except json.JSONDecodeError:
        # Find the last complete object and close the array
        last_close = content.rfind('}')
        if last_close != -1:
            content = content[:last_close + 1] + ']'
        plans = json.loads(content)

    # Save to a content calendar file
    path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_calendar.json"
    with open(path, "w") as f:
        json.dump(plans, f, indent=2)

    print(f"✓ Saved {len(plans)} post ideas to content calendar")
    return plans
