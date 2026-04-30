"""
Write all mocktail/NA marketing assets:
- Instagram content series
- NA partnership deck
- NA-specific press release
- Mocktail SEO landing pages
"""
import anthropic, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
OUT = Path('marketing_assets/mocktails')
OUT.mkdir(parents=True, exist_ok=True)
APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"


# ── 1. Instagram Mocktail Content Series ──────────────────────────────────────
resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=3000,
    messages=[{"role": "user", "content": f"""Write a 10-post Instagram content series for Spirit Library's mocktail/non-alcoholic campaign.

Context: Spirit Library is an iOS cocktail app with 1,700+ recipes. We're expanding our non-alcoholic section. The sober-curious movement is massive — Dry January grew 30% year-over-year, Gen Z drinks 20% less than millennials.

The series should:
- Normalize not drinking without being preachy
- Showcase that NA drinks can be just as sophisticated and delicious
- Feature specific mocktail recipes with full ingredients and steps
- Mix educational, recipe, and lifestyle posts
- Use the same premium aesthetic as our cocktail content
- Drive downloads via Spirit Library's features (Flavor Search, My Bar, Occasion Search all work for NA)

For each post write:
1. POST TYPE (recipe / educational / lifestyle / engagement)
2. CAPTION (150-280 chars, conversational, sophisticated)
3. IMAGE PROMPT (Imagen 4 Ultra — photorealistic, no text in image, same editorial quality as cocktail photography)
4. HASHTAGS (8-12, mix of NA-specific and general cocktail tags)

Include these specific mocktails:
- Seedlip Garden Spritz
- Espresso Tonic (NA)
- Cucumber Gimlet (NA)
- Spicy Paloma (NA)
- Lavender Collins (NA)
Plus 5 more creative NA drinks.

App Store: {APP_STORE}"""}]
)
(OUT / "instagram_series.txt").write_text(resp.content[0].text)
print("✓ Mocktail Instagram series → mocktails/instagram_series.txt")


# ── 2. NA Partnership Pitch Deck ──────────────────────────────────────────────
resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2500,
    messages=[{"role": "user", "content": f"""Write a partnership pitch document for Spirit Library targeting non-alcoholic spirits brands.

Context:
- Spirit Library: iOS cocktail app, 1,700+ recipes, free
- Expanding NA/mocktail section
- Audience: cocktail enthusiasts 25-45, increasingly sober-curious
- Features: My Bar, Flavor Search, Occasion Search, Share Menus, Allergies filter — all work for NA

Market data to reference:
- Non-alcoholic spirits market growing 30%+ annually
- Dry January participation up 30% YoY
- Gen Z drinks 20% less alcohol than millennials
- 78% of NA spirit consumers also buy alcoholic spirits (they're the same audience)
- NA spirits market projected to hit $30B by 2030

Write a 1-page pitch with:
1. THE OPPORTUNITY: Why cocktail apps are the perfect distribution channel for NA brands
2. WHAT WE OFFER:
   - Custom NA recipes featuring their spirit (permanent in-app)
   - Cocktail of the Day NA sponsorship ($500/month founding rate)
   - Ingredient Search placement (user searches "non-alcoholic gin" → their brand appears)
   - Share Menus integration (hosts can share NA menus for inclusive gatherings)
3. WHY NOW: First-mover advantage in an untapped channel
4. TIERS:
   - Discovery: $500/month (3 recipes + ingredient listing)
   - Featured: $1,000/month (above + Cocktail of the Day sponsorship + social cross-promotion)
   - Exclusive: $2,000/month (above + category lock + Share Menus featured brand)
5. NEXT STEPS

Make it feel premium and data-driven. This goes to NA brand marketing teams who are flooded with partnership pitches — it needs to stand out."""}]
)
(OUT / "partnership_deck.txt").write_text(resp.content[0].text)
print("✓ NA partnership deck → mocktails/partnership_deck.txt")


# ── 3. NA-Specific Press Release ─────────────────────────────────────────────
resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2000,
    messages=[{"role": "user", "content": f"""Write a press release about Spirit Library expanding its non-alcoholic cocktail section.

Facts:
- Spirit Library: iOS cocktail app with 1,700+ recipes, live on App Store
- Founded by Steven Samori
- Expanding dedicated non-alcoholic/mocktail recipe section
- All existing features (My Bar, Flavor Search, Occasion Search, Allergies filter) work seamlessly for NA drinks
- Partnering with NA spirit brands (Seedlip, Lyre's, Monday, Ghia, Ritual, etc.) to feature their products
- Cocktail of the Day now includes an NA category
- Share Menus feature allows hosts to create inclusive menus mixing alcoholic and non-alcoholic drinks

Headline: Something that positions this as a market shift, not just a feature update
Dateline: New York, April 11, 2026
Angle: The first major cocktail app to take non-alcoholic drinks as seriously as the real thing
Include: market size data, sober-curious trend, founder quote about inclusivity
Contact: Steven Samori, claudesonnet111@gmail.com
App Store: {APP_STORE}

Voice: editorial, confident, newsworthy. Publishable in Food & Wine or VinePair."""}]
)
(OUT / "press_release.txt").write_text(resp.content[0].text)
print("✓ NA press release → mocktails/press_release.txt")


# ── 4. Mocktail SEO Landing Pages ─────────────────────────────────────────────
MOCKTAILS_SEO = [
    ("best-mocktail-recipes", "Best Mocktail Recipes", "mocktails, non-alcoholic cocktails, mocktail recipes"),
    ("seedlip-cocktails", "Seedlip Cocktail Recipes", "Seedlip recipes, non-alcoholic gin cocktails"),
    ("dry-january-cocktails", "Dry January Cocktail Recipes", "Dry January drinks, non-alcoholic January"),
    ("non-alcoholic-cocktails-for-parties", "Non-Alcoholic Cocktails for Parties", "party mocktails, NA party drinks"),
    ("mocktails-with-ingredients-at-home", "Mocktails You Can Make at Home Right Now", "easy mocktails, home mocktail recipes"),
]

for slug, title, keywords in MOCKTAILS_SEO:
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": f"""Write an SEO-optimized landing page for "{title}".
Target keywords: {keywords}
Spirit Library app: {APP_STORE} (free iOS app, 1,700+ cocktail recipes including mocktails)

Write in Markdown:
1. H1: "{title}"
2. Intro paragraph with keywords
3. H2: "Top 5 {title.split(' ')[0]} Recipes" with 5 specific named mocktails, each with ingredients list and brief instructions
4. H2: "Tips for Making Great Mocktails" (3-4 tips)
5. H2: "Find These Recipes in Spirit Library" — natural CTA, not salesy

600-800 words. Warm, knowledgeable, helpful."""}]
    )
    (OUT / f"seo_{slug}.md").write_text(resp.content[0].text)
    print(f"✓ SEO: {title} → mocktails/seo_{slug}.md")


# ── 5. Email drip sequence for NA brands ──────────────────────────────────────
resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2000,
    messages=[{"role": "user", "content": f"""Write a 3-email drip sequence for non-alcoholic spirit brands who don't respond to the initial partnership pitch.

Context: We already sent an initial email about featuring their NA spirit in Spirit Library's recipe database and Cocktail of the Day sponsorship.

Email 1 (Day 7 — value add):
- Subject line
- 100-150 words
- Share a new data point or insight about the NA market
- Mention that their competitors are in conversations (social proof)

Email 2 (Day 14 — exclusivity urgency):
- Subject line
- 80-100 words
- Mention the category lock is filling up
- Offer to send a custom recipe demo featuring their specific spirit

Email 3 (Day 21 — breakup email):
- Subject line
- 50-60 words
- Last touch, leave the door open
- Mention you're moving on to their competitor in the category

All from Steven Samori, founder. Personal voice, not corporate."""}]
)
(OUT / "email_drip_sequence.txt").write_text(resp.content[0].text)
print("✓ NA email drip → mocktails/email_drip_sequence.txt")


print(f"\n✅ All mocktail marketing assets complete!")
print(f"\nFiles created:")
for f in sorted(OUT.glob("*")):
    if f.is_file():
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")
