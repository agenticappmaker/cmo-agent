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


def generate_post(brand_slug: str, platform: str = "instagram") -> dict:
    """
    Autonomously generate a complete post for the given brand and platform.
    Returns: { caption, hashtags, image_prompt, post_idea, pillar }
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    brand = load_brand(brand_slug)
    config = brand["config"]
    knowledge = brand["knowledge"]
    history = brand["history"]

    # Build recent post summary to avoid repetition
    recent = ""
    if history:
        recent_posts = history[-10:]
        recent = "\n".join([
            f"- {p.get('post_idea', 'unknown')} ({p.get('pillar', 'unknown')})"
            for p in recent_posts
        ])
        recent = f"\n\nRecent posts (avoid repeating these topics):\n{recent}"

    # Pick random hashtags from pool (5-8 from pool + all core)
    pool = config.get("hashtags_pool", [])
    core = config.get("hashtags_core", [])
    selected_pool = random.sample(pool, min(7, len(pool)))
    all_tags = core + selected_pool

    platform_guidance = {
        "instagram": "Instagram post: caption 150-280 chars, engaging, 1-2 emojis ok. Spotlight a specific cocktail recipe — name it, describe it, make it sound irresistible. Hashtags will be appended separately.",
        "facebook":  "Facebook post: conversational, 100-230 chars. Spotlight a specific cocktail recipe — name it, give a tasting note or fun fact. Friendly tone, 1 emoji max.",
        "linkedin":  "LinkedIn post: professional but warm, 150-280 chars. Frame a cocktail spotlight as an entertaining/hospitality insight or trend.",
        "twitter":   "X/Twitter post: punchy, max 200 chars. Name the cocktail, one sharp line about it. Hook immediately.",
        "tiktok":    "TikTok caption: 100-140 chars, energetic hook. Spotlight a cocktail, make it sound fun and easy to make.",
    }.get(platform, "")

    CTA = "\n\nComment below your favorite recipes!\n\nSave and share entire menus with Spirit Library in the App Store!!!"

    prompt = f"""You are the autonomous CMO agent for {config['brand_name']}.

BRAND KNOWLEDGE:
{knowledge}

BRAND TONE: {config['tone']}
TARGET AUDIENCE: {config['target_audience']}
CONTENT PILLARS: {', '.join(config['content_pillars'])}
PLATFORM: {platform}
{platform_guidance}
{recent}

Your job:
1. Choose a SPECIFIC cocktail recipe to spotlight — pick one that hasn't been featured in recent posts. Be specific (e.g. "Paper Plane", "Naked & Famous", "Oaxacan Old Fashioned").
2. Write the perfect caption for {platform} — name the cocktail, make it sound incredible
3. Write a detailed image generation prompt (for DALL-E) showing that specific cocktail beautifully
4. Choose the most relevant content pillar
IMPORTANT: The caption must NOT include a CTA — it will be appended automatically.

Respond in this exact JSON format:
{{
  "post_idea": "one sentence describing the post concept",
  "pillar": "which content pillar this falls under",
  "caption": "the full caption text (no hashtags)",
  "image_prompt": "detailed DALL-E prompt for the post image — cinematic, specific, high quality",
  "reasoning": "why you chose this topic today"
}}"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    content = message.content[0].text.strip()
    # Strip markdown code blocks if present
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

    plans = json.loads(content)

    # Save to a content calendar file
    path = Path(__file__).parent.parent / "posts" / f"{brand_slug}_calendar.json"
    with open(path, "w") as f:
        json.dump(plans, f, indent=2)

    print(f"✓ Saved {len(plans)} post ideas to content calendar")
    return plans
