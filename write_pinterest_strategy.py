"""
Write a full Pinterest strategy for Spirit Library.
Pinterest is Tier 3 but has massive SEO value — pins rank on Google Images
and drive long-tail cocktail traffic for years.
"""
import anthropic, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
OUT = Path('marketing_assets')
APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"

resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=3000,
    messages=[{"role": "user", "content": f"""Write a complete Pinterest marketing strategy for Spirit Library (iOS cocktail app, 1,700+ recipes, free).

App Store: {APP_STORE}
Website (coming): spiritlibraryapp.com

Why Pinterest matters for Spirit Library:
- Cocktail content performs exceptionally on Pinterest (recipe searches are its #1 category)
- Pins have a 6-month average lifespan vs. 48 hours on Instagram
- Pinterest drives Google-indexed traffic — pins rank in Google Image search
- 85% of users use Pinterest to plan purchases/experiences

Write:

## 1. BOARD STRUCTURE
List 10 Pinterest boards to create with:
- Board name (keyword-optimized)
- Description (160 chars, keyword-rich)
- What to pin there

## 2. PIN TEMPLATES (5 designs to create)
For each: dimensions, visual description, text overlay copy, and the SEO keyword it targets.
Spirit Library's images are photorealistic Imagen 4 photos — describe how to format them as pins.

## 3. FIRST 30 PINS TO CREATE
List 30 specific pins with:
- Title (100 chars, keyword-rich)
- Description (500 chars max, includes call to action and App Store link)
- Which board it goes on
- Target keyword

## 4. PINNING SCHEDULE
How many pins per day, what times, tools to use (Tailwind, manual, etc.)

## 5. SEO KEYWORDS FOR PINTEREST
Top 20 keywords Spirit Library should target on Pinterest — based on cocktail search volume.

## 6. RICH PINS SETUP
How to enable Rich Pins for the spiritlibraryapp.com website to get better distribution.

Be extremely specific — this should be executable immediately."""}]
)

(OUT / "pinterest_strategy.txt").write_text(resp.content[0].text)
print("✓ Pinterest strategy → marketing_assets/pinterest_strategy.txt")
