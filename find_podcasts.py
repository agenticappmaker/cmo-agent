"""
Find cocktail/spirits/food-tech podcasts for Spirit Library guest appearances
and sponsorship opportunities.
"""
import anthropic, os, json, re, time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

PODCAST_FILE = Path('outreach/targets/podcasts.json')

podcasts = [
    "Cocktail College (Food52)",
    "The Speakeasy podcast",
    "Whiskey Lore podcast",
    "The Dram Good Show",
    "Good Food podcast (KCRW)",
    "Drinks with Parents",
    "The Cocktail Guru Project",
    "Bartender at Large",
    "The Bitter Truth podcast",
    "How I Built This (NPR) — for founder story angle",
    "Product Hunt Radio",
    "Masters of Scale",
    "StartUp podcast (Gimlet)",
    "My First Million podcast",
    "The Founder Hour",
]

results = []
print(f"\n🎙️ Researching {len(podcasts)} podcasts for Spirit Library...\n")

for i, podcast in enumerate(podcasts, 1):
    prompt = f"""From your training knowledge, provide contact and booking info for the podcast "{podcast}".

I want to pitch Spirit Library (iOS cocktail app, 1,700+ recipes, AI-powered ingredient search) as either:
- A guest (Steven Samori, founder, talking about building a cocktail app)
- A sponsor/advertiser
- A featured product review

From training knowledge, provide:
1. Host name(s)
2. Known booking/pitch email or typical submission method for this show
3. Estimated audience size
4. What topics this podcast typically covers
5. Fit assessment for Spirit Library

Return ONLY this JSON:
{{
  "podcast": "{podcast}",
  "host_name": "...",
  "audience_size": "...",
  "booking_email": "email or null",
  "submission_url": "URL or null",
  "recent_topics": "brief description",
  "fit_score": "high/medium/low",
  "pitch_angle": "one-sentence pitch angle for this specific show",
  "outreach_type": "email or form"
}}"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            
            messages=[{"role": "user", "content": prompt}]
        )
        text = ""
        for block in resp.content:
            if hasattr(block, "text") and block.text.strip():
                text = block.text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            result = json.loads(match.group())
            result['researched_at'] = datetime.utcnow().isoformat()
            results.append(result)
            print(f"  [{i}/{len(podcasts)}] ✓ {podcast}: {result.get('booking_email','no email')} [{result.get('fit_score','?')}]")
        else:
            print(f"  [{i}/{len(podcasts)}] ? {podcast}: no data")
        time.sleep(5)
    except Exception as e:
        print(f"  [{i}/{len(podcasts)}] ✗ {e}")
        time.sleep(5)

PODCAST_FILE.parent.mkdir(exist_ok=True)
PODCAST_FILE.write_text(json.dumps(results, indent=2))
print(f"\n✅ Found {len(results)} podcast contacts → {PODCAST_FILE}")
