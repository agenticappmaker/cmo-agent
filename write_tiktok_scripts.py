"""
Write 10 TikTok video scripts for Spirit Library.
High-virality formats: POV, tutorial, reaction, "hack", trend-hook.
"""
import anthropic, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
OUT = Path('marketing_assets')
APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"

prompt = f"""Write 10 TikTok video scripts for Spirit Library (iOS cocktail app, 1,700+ recipes, free).

Key features to showcase naturally:
- My Bar: add your bottles → see every cocktail you can make
- Flavor Search: filter by Citrus, Bitter, Smoky, Herbal, Tropical, etc.
- Share Menus: curate and send a cocktail menu to guests before a party
- Allergies filter: filter cocktails by allergen
- 1,700+ recipes

Use these proven TikTok formats (mix them up):
1. POV format: "POV: you finally have a use for that bottle of..."
2. "I tried making X using only what I had in my bar..."
3. Ranking format: "Rating the 5 most overrated cocktails"
4. Tutorial: "30-second [cocktail name] tutorial"
5. Reaction: "Testing TikTok's most viral cocktail recipes"
6. Hack: "The bartender secret nobody tells you about [technique]"
7. Story: "I built a cocktail app because I was tired of..."
8. Before/After: "My home bar before vs. after Spirit Library"
9. Trend hook: "[Trending audio/sound] but it's cocktail edition"
10. Debate starter: "Controversial opinion: the [cocktail] is overrated and here's why"

For each script write:
- TITLE/HOOK (first 3 seconds — this is everything on TikTok)
- SCRIPT (what to say, shot by shot, 30-60 second target)
- ON-SCREEN TEXT suggestions
- HASHTAGS (8-12, mix of size)
- CTA (last 5 seconds)
- TRENDING AUDIO suggestion (describe the type of audio, not specific song)

App Store: {APP_STORE}

Make the scripts feel authentic and native to TikTok — not like ads. The best performing content feels like a creator naturally discovered the app and is sharing it."""

resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=4000,
    messages=[{"role": "user", "content": prompt}]
)
text = resp.content[0].text
(OUT / "tiktok_scripts.txt").write_text(text)
print(f"✓ 10 TikTok scripts → marketing_assets/tiktok_scripts.txt")
print(f"\nPreview of Script 1:\n")
print(text[:500] + "...")
