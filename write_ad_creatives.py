"""
Write all ad creative scripts and copy — ready to activate the day Apple approves.
Meta Reels scripts, Apple Search Ads copy, TikTok Spark briefs.
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
    max_tokens=4000,
    messages=[{"role": "user", "content": f"""Write a complete ad creative package for Spirit Library (iOS cocktail app, 1,700+ recipes, free).

App Store: {APP_STORE}
Founder: Steven Samori
Key features: My Bar (add bottles → see what you can make), Flavor Search, Occasion Search, Allergies filter, Share Menus

## SECTION 1: APPLE SEARCH ADS COPY
Write 5 ad variations for Apple Search Ads (title + subtitle format):
- Title: 30 chars max
- Subtitle: 45 chars max
Each should target a different keyword intent (ingredient search, occasion, flavor, sharing, recipe discovery)

## SECTION 2: META REELS SCRIPTS (5 scripts)
For each: Hook (first 3 sec) + Script (15-30 sec) + On-screen text + CTA
Formats to cover:
1. My Bar feature demo — "I have a full bar and no idea what to make" problem/solution
2. ASMR cocktail pour — visual, minimal speech, high completion rate
3. Share Menus — "send your guests the menu before they arrive"
4. Occasion search — "what to make for [occasion]"
5. Founder story — Steven built this because he was frustrated with Google searches for cocktails

## SECTION 3: META STATIC AD COPY (3 variations)
Headline + Primary text + CTA button text
For Facebook/Instagram feed ads, targeting home entertainers and cocktail enthusiasts

## SECTION 4: TIKTOK SPARK AD BRIEF
A one-paragraph brief for what organic TikTok content to post and boost as Spark Ads.
Which content to create, what metrics indicate it's worth boosting, and the boost settings.

## SECTION 5: LAUNCH DAY CHECKLIST
A sequenced checklist for the day Apple approves the app — exactly what to do in what order to maximize the launch window.

Be extremely specific and actionable. These are ready-to-use scripts, not concepts."""}]
)

(OUT / "ad_creatives_ready.txt").write_text(resp.content[0].text)
print("✓ Ad creatives → marketing_assets/ad_creatives_ready.txt")
print(resp.content[0].text[:300] + "...")
