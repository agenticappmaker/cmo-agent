"""
Outreach Generator — uses Claude to write tailored partnership pitches
for each researched target. Writes emails to outbox.json and DMs to dm_queue.json.
"""

import anthropic
import json
import os
import re
from datetime import datetime
from pathlib import Path

OUTREACH_DIR = Path(__file__).parent.parent / "outreach"
CACHE_FILE = OUTREACH_DIR / "research_cache.json"
OUTBOX_FILE = OUTREACH_DIR / "outbox.json"
DM_QUEUE_FILE = OUTREACH_DIR / "dm_queue.json"

SENDER_NAME = "Steven Samori"
APP_NAME = "Spirit Library"
APP_STORE_URL = "https://apps.apple.com/app/id6746823938"

APP_FEATURES_BRIEF = """
Spirit Library (iOS) — 1,700+ cocktail recipes:
• MY BAR: add your spirits/mixers, search by ingredient AND flavor to find what you can make now
• FLAVOR SEARCH: filter by Smoky, Bitter, Citrus, Floral, Tropical, Herbal, etc.
• CREATE YOUR OWN: build & save custom cocktail recipes, share them
• SHARE MENUS: curate and share full cocktail menus with guests or customers
• COCKTAIL OF THE DAY: daily featured spotlight (open for brand sponsorship)
• SHOPPING CART (coming soon): buy ingredients via Instacart, DoorDash, Uber Eats directly from recipe
"""


def _load_json(path: Path) -> list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def _save_json(path: Path, data):
    OUTREACH_DIR.mkdir(exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _extract_json(text: str) -> dict:
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
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return json.loads(match.group())
        raise


def _write_email_pitch(client, profile: dict) -> dict:
    """Generate a tailored email pitch for a brand/company/media target."""
    name = profile.get("name", "")
    what_they_do = profile.get("what_they_do", "")
    recent_activity = profile.get("recent_activity", "")
    partnership_idea = profile.get("partnership_idea", "")
    best_feature = profile.get("best_feature_to_pitch", "")
    why_care = profile.get("why_they_should_care", "")
    category = profile.get("category", "")

    # Tailor tone by category
    if category in ("delivery", "grocery_delivery", "food_delivery", "alcohol_delivery", "convenience_delivery", "specialty_grocery", "alcohol_retail"):
        tone_guidance = "Professional B2B tone. This is a business development pitch proposing an API/affiliate integration. Be specific about the revenue/traffic opportunity."
    elif category in ("cocktail_media", "drinks_media", "food_drink_media"):
        tone_guidance = "Editorial pitch tone. Offer something newsworthy (app review, exclusive feature, partnership announcement). Be concise and journalist-friendly."
    elif category in ("spirits_brand", "mixer_brand", "bitters_brand"):
        tone_guidance = "Brand partnership tone. Lead with the user reach and the specific feature that showcases their product. Mention Cocktail of the Day sponsorship or ingredient search as the hook."
    else:
        tone_guidance = "Professional but warm. Lead with their specific work, tie it directly to Spirit Library."

    prompt = f"""You are writing a personalized partnership outreach EMAIL for Spirit Library.

{APP_FEATURES_BRIEF}

RESEARCHED TARGET PROFILE:
Name: {name}
What they do: {what_they_do}
Recent activity: {recent_activity}
Best feature to pitch: {best_feature}
Concrete partnership idea: {partnership_idea}
Why they should care: {why_care}

TONE: {tone_guidance}

Write a targeted partnership pitch email. Requirements:
- Subject line: specific, not generic, references their brand by name
- Opening line: reference something SPECIFIC about them from the profile (recent activity, what they do)
- Connect Spirit Library's "{best_feature}" directly to their work in 2-3 sentences
- State the partnership idea clearly: {partnership_idea}
- What's in it for them: {why_care}
- CTA: one clear ask (15-min call, reply to explore, etc.)
- Close from {SENDER_NAME}, Founder of {APP_NAME}
- Total length: 180-280 words (tight, no fluff)
- NO exclamation points in the subject line
- Do NOT mention competitors

Respond as JSON ONLY:
{{
  "subject": "email subject line",
  "body": "full email body (plain text, use line breaks between paragraphs)",
  "key_hook": "one-line summary of the main value prop used",
  "confidence": "high/medium/low — how confident are you this angle will resonate"
}}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )
    return _extract_json(response.content[0].text)


def _write_dm_pitch(client, profile: dict) -> dict:
    """Generate a short, friendly Instagram/TikTok DM pitch."""
    name = profile.get("name", "")
    handle = profile.get("handle", "")
    what_they_do = profile.get("what_they_do", "")
    recent_activity = profile.get("recent_activity", "")
    best_feature = profile.get("best_feature_to_pitch", "")
    partnership_idea = profile.get("partnership_idea", "")

    prompt = f"""You are writing a SHORT Instagram DM from {SENDER_NAME}, founder of Spirit Library.

{APP_FEATURES_BRIEF}

TARGET: @{handle} — {name}
What they do: {what_they_do}
Recent activity: {recent_activity}
Feature to pitch: {best_feature}
Partnership idea: {partnership_idea}

Write a genuine, short DM (100-180 words MAX). Rules:
- Open with something SPECIFIC about their content (not "I love your content" — actually say what specific thing)
- 1-2 sentences max introducing Spirit Library and the ONE feature relevant to them
- Mention the partnership idea briefly
- End with a low-pressure question to get a reply (e.g. "Would you be open to chatting?")
- Tone: human, direct, NOT salesy or corporate. Like a real person reaching out.
- Max 1-2 emojis, used naturally
- Do NOT say "I came across your profile" — too generic
- Sign off with first name only: Steven

Respond as JSON ONLY:
{{
  "body": "the full DM text",
  "key_hook": "the specific thing you referenced about them",
  "platform": "instagram or tiktok"
}}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )
    return _extract_json(response.content[0].text)


def draft_all_pitches(force_refresh: bool = False, category_filter: str = None):
    """
    Generate pitches for all researched targets.
    Saves emails → outbox.json, DMs → dm_queue.json.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if not CACHE_FILE.exists():
        print("No research cache found. Run: python main.py outreach research")
        return [], []

    with open(CACHE_FILE) as f:
        cache = json.load(f)

    outbox = _load_json(OUTBOX_FILE)
    dm_queue = _load_json(DM_QUEUE_FILE)

    drafted_emails = {m["target_key"] for m in outbox}
    drafted_dms = {m["target_key"] for m in dm_queue}

    targets = [v for v in cache.values() if "error" not in v]

    if category_filter:
        targets = [t for t in targets if t.get("_source_file", "") == category_filter
                   or t.get("category", "") == category_filter]

    print(f"\n✍️  Drafting pitches for {len(targets)} researched targets...")

    for i, profile in enumerate(targets, 1):
        target_key = profile.get("handle") or profile.get("name", f"target_{i}")
        outreach_type = profile.get("outreach_type", "email")

        already_drafted = (
            (outreach_type == "email" and target_key in drafted_emails) or
            (outreach_type == "dm" and target_key in drafted_dms)
        )

        if already_drafted and not force_refresh:
            print(f"  [{i}/{len(targets)}] ⏭  {target_key} (already drafted)")
            continue

        print(f"  [{i}/{len(targets)}] ✍️  {target_key} ({outreach_type})...")

        try:
            if outreach_type == "dm":
                pitch = _write_dm_pitch(client, profile)
                entry = {
                    "target_key": target_key,
                    "name": profile.get("name", target_key),
                    "handle": profile.get("handle", ""),
                    "category": profile.get("category", ""),
                    "platform": pitch.get("platform", profile.get("platform", "instagram")),
                    "outreach_type": "dm",
                    "body": pitch.get("body", ""),
                    "key_hook": pitch.get("key_hook", ""),
                    "status": "ready",
                    "drafted_at": datetime.utcnow().isoformat(),
                    "sent_at": None
                }
                dm_queue = [m for m in dm_queue if m["target_key"] != target_key]
                dm_queue.append(entry)
                _save_json(DM_QUEUE_FILE, dm_queue)
            else:
                pitch = _write_email_pitch(client, profile)
                entry = {
                    "target_key": target_key,
                    "name": profile.get("name", target_key),
                    "handle": profile.get("handle", ""),
                    "category": profile.get("category", ""),
                    "contact_email": profile.get("contact_email") or "",
                    "outreach_type": "email",
                    "subject": pitch.get("subject", ""),
                    "body": pitch.get("body", ""),
                    "key_hook": pitch.get("key_hook", ""),
                    "confidence": pitch.get("confidence", "medium"),
                    "status": "draft",
                    "drafted_at": datetime.utcnow().isoformat(),
                    "sent_at": None
                }
                outbox = [m for m in outbox if m["target_key"] != target_key]
                outbox.append(entry)
                _save_json(OUTBOX_FILE, outbox)

            print(f"      ✓ Hook: {pitch.get('key_hook', '')[:70]}")

        except Exception as e:
            print(f"      ✗ Error drafting for {target_key}: {e}")

    # Print summary
    ready_emails = [e for e in outbox if e["status"] == "draft" and e.get("contact_email")]
    missing_email = [e for e in outbox if e["status"] == "draft" and not e.get("contact_email")]
    ready_dms = [d for d in dm_queue if d["status"] == "ready"]

    print(f"\n📬 Draft summary:")
    print(f"   Emails ready to send: {len(ready_emails)}")
    print(f"   Emails missing contact address: {len(missing_email)}")
    print(f"   DMs ready to copy/send: {len(ready_dms)}")

    return outbox, dm_queue


def show_outbox():
    """Print the full outbox contents."""
    outbox = _load_json(OUTBOX_FILE)
    if not outbox:
        print("Outbox is empty. Run: python main.py outreach draft")
        return

    print(f"\n📬 EMAIL OUTBOX ({len(outbox)} total)\n")
    for e in outbox:
        status_icon = "✓" if e["status"] == "sent" else ("⚠" if not e.get("contact_email") else "→")
        print(f"{status_icon} [{e['status'].upper()}] {e['name']}")
        print(f"   To: {e.get('contact_email') or 'NO EMAIL FOUND'}")
        print(f"   Subject: {e.get('subject', '')}")
        print(f"   Hook: {e.get('key_hook', '')}")
        if e.get("sent_at"):
            print(f"   Sent: {e['sent_at'][:10]}")
        print()


def show_dm_queue(platform_filter: str = None):
    """Print all DMs ready to send."""
    dm_queue = _load_json(DM_QUEUE_FILE)
    if not dm_queue:
        print("DM queue is empty. Run: python main.py outreach draft")
        return

    if platform_filter:
        dm_queue = [d for d in dm_queue if d.get("platform") == platform_filter]

    pending = [d for d in dm_queue if d["status"] != "sent"]
    sent = [d for d in dm_queue if d["status"] == "sent"]

    print(f"\n💬 DM QUEUE — {len(pending)} pending, {len(sent)} sent\n")
    print("=" * 70)

    for d in pending:
        platform = d.get("platform", "instagram").upper()
        print(f"\n📲 [{platform}] @{d.get('handle', d['name'])}")
        print(f"   Category: {d.get('category', '')}")
        print(f"   Hook: {d.get('key_hook', '')}")
        print(f"\n--- COPY THIS MESSAGE ---")
        print(d.get("body", ""))
        print("--- END ---\n")
        print("-" * 70)
