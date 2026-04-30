"""
Generate all marketing assets: press release, ASO copy, Reddit posts,
Product Hunt submission, sponsorship deck, influencer pitch, Share Menus campaign.
"""
import anthropic, os, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
OUT = Path('marketing_assets')
OUT.mkdir(exist_ok=True)

APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"

def generate(prompt, filename, label):
    print(f"\n✍️  Writing {label}...")
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    text = resp.content[0].text
    (OUT / filename).write_text(text)
    print(f"   ✓ Saved → marketing_assets/{filename}")
    return text


# ── 1. Press Release ──────────────────────────────────────────────────────────
generate(f"""Write a professional press release for Spirit Library, a new iOS cocktail app.

Facts:
- App name: Spirit Library
- Founded by: Steven Samori
- Available: App Store ({APP_STORE})
- 1,700+ cocktail recipes spanning all major spirits
- Key features: My Bar (add your bottles, discover what you can make), Flavor Search, Occasion Search, Share Menus (share curated cocktail menus with guests), Create Your Own Cocktail, Substitutions tab (140+ substitutions), Cocktail of the Day
- Allergies filter — filter all cocktails by allergen (nuts, dairy, gluten, etc.)
- Android coming soon
- Future: Shopping cart integration with Instacart/DoorDash (order cocktail ingredients in-app)
- Target user: cocktail enthusiasts aged 25-45, home bartenders, hosts

Write a proper press release with:
- Headline (attention-grabbing, editorial quality)
- Dateline: New York, April 9, 2026
- Lede paragraph (who, what, when, where, why)
- 3-4 body paragraphs covering features, market opportunity, and founder quote
- Boilerplate about Spirit Library
- Contact info: Steven Samori, claudesonnet111@gmail.com

Voice: confident, editorial, not salesy. This should be publishable in TechCrunch or Food & Wine.""",
"press_release.txt", "Press Release")


# ── 2. App Store Optimization ─────────────────────────────────────────────────
generate(f"""Write an optimized App Store description for Spirit Library.

App facts:
- 1,700+ cocktail recipes
- My Bar: add your bottles, find what you can make RIGHT NOW
- Flavor Search: filter by Spirit-forward, Citrus, Sweet, Bitter, Herbal, Smoky, Tropical, Creamy, Spicy, Floral, Fruity, Refreshing, Rich, Dry, Effervescent
- Occasion Search: Date Night, Party, After Dinner, Brunch, Summer, Winter, Celebration, Relaxing, Happy Hour
- Allergies filter: filter by nuts, dairy, gluten, eggs, soy, citrus, shellfish
- Share Menus: curate and share cocktail menus with guests
- Create Your Own Cocktail: full recipe builder
- Cocktail of the Day: daily featured cocktail
- Substitutions: 140+ substitution suggestions
- Free, iOS only, Android coming soon
- App Store URL: {APP_STORE}

Write:
1. SHORT DESCRIPTION (170 chars max) — punchy, keyword-rich
2. FULL DESCRIPTION (4,000 chars max) — covers all features, benefit-led language, natural keyword inclusion
   Include: cocktail recipes, cocktail app, home bar, mixology, drink recipes, bartending, cocktail maker
3. KEYWORDS field (100 chars max, comma-separated, no spaces after commas)
4. SUBTITLE (30 chars max) — shown under app name in search

Optimize for App Store search. Lead with the user benefit, not the feature name.""",
"app_store_aso.txt", "App Store ASO Copy")


# ── 3. Reddit Posts ───────────────────────────────────────────────────────────
generate("""Write 5 Reddit posts for r/cocktails and r/mixology that provide genuine value and naturally mention Spirit Library.

Rules:
- NO hard selling. These must feel like authentic community contributions.
- Lead with value (recipe, tip, knowledge) — mention the app only if it flows naturally
- Reddit community is savvy and hates obvious promotion
- Each post needs: Title + Body
- Mix formats: recipe post, question starter, tip/technique, history/trivia, recommendation request

Write 5 distinct posts. Make them genuinely interesting to cocktail enthusiasts. If Spirit Library is mentioned, it should feel incidental ("I built a cocktail app and here's what I learned...") not promotional.""",
"reddit_posts.txt", "Reddit Posts")


# ── 4. Product Hunt Submission ────────────────────────────────────────────────
generate(f"""Write a Product Hunt submission for Spirit Library.

App facts:
- Spirit Library: iOS cocktail app, 1,700+ recipes
- My Bar feature: add your bottles → discover what you can make
- Flavor Search, Occasion Search, Allergies filter
- Share Menus: digital cocktail menus for hosting
- Create your own cocktails
- Founder: Steven Samori
- App Store: {APP_STORE}

Write:
1. TAGLINE (60 chars max): one-line description, compelling
2. DESCRIPTION (260 chars): what it does, for whom, why it's different
3. FIRST COMMENT (founder comment, 300-500 words): tell the story of why you built it, what problem it solves, what makes it different. Personal, honest, founder voice. End with a genuine ask for feedback.
4. TOPICS: list 5 relevant Product Hunt topics/tags""",
"product_hunt.txt", "Product Hunt Submission")


# ── 5. Cocktail of the Day Sponsorship Deck ───────────────────────────────────
generate(f"""Write a one-page sponsorship proposal for Spirit Library's "Cocktail of the Day" feature.

Context:
- Spirit Library is a cocktail app with 1,700+ recipes, live on iOS
- Cocktail of the Day: a daily featured cocktail seen by all active users in the app
- We're offering founding sponsor pricing to 1 spirits brand per spirit category
- The sponsor's brand appears in the daily cocktail image, caption, and gets linked
- Categories available: Gin, Tequila, Whiskey/Bourbon, Rum, Mezcal, Vodka, Brandy

Write a proposal that covers:
1. What the opportunity is (short, punchy description)
2. Why it matters (audience: cocktail enthusiasts 25-45, engaged, purchase-intent)
3. What's included (daily feature, brand imagery, category exclusivity, social cross-post)
4. Pricing tiers:
   - Founding Sponsor: $500/month (1 category, locked in for 6 months)
   - Standard: $1,500/month
   - Premium (includes Share Menus): $3,000/month
5. Next steps: reply to schedule a call

Tone: confident, direct, premium. This goes to spirits brand marketing teams. Make them feel like they're getting in early on something that will be big.""",
"sponsorship_deck.txt", "Sponsorship Deck")


# ── 6. Influencer Pitch Email Template ────────────────────────────────────────
generate(f"""Write 3 influencer pitch email templates for Spirit Library — one for each tier:

Tier 1 (Nano/Micro, 5k-50k followers): cocktail home enthusiast creators
Tier 2 (Mid-tier, 50k-500k): cocktail/food/lifestyle creators
Tier 3 (Macro, 500k+): celebrity bartenders, celebrity chefs with cocktail content

For each:
- Subject line
- Email body (150-200 words max)
- What we're offering: free featured cocktail collab (we'll create a custom cocktail in their name inside the app), app credit, potential paid partnership
- NOT asking them to post yet — just opening a conversation
- Personalization placeholder: [NAME], [THEIR_SIGNATURE_COCKTAIL], [THEIR_PLATFORM]

Voice: peer-to-peer, not brand-to-influencer. Steven is a founder who loves cocktails, not a marketing department.""",
"influencer_pitches.txt", "Influencer Pitches")


# ── 7. Share Menus Viral Campaign ────────────────────────────────────────────
generate(f"""Design a viral growth campaign around Spirit Library's Share Menus feature.

Share Menus: Users curate a cocktail menu inside the app and share a link with guests before a dinner party, event, or gathering. Guests click the link, see the menu, and can download Spirit Library to explore more.

Design a complete campaign:

1. CAMPAIGN NAME & CONCEPT (2-3 sentences, the big idea)

2. TARGET OCCASIONS (specific moments when sharing a menu makes sense): list 8 specific occasions with a 1-sentence hook for each

3. SOCIAL CONTENT IDEAS: 5 specific posts/reels concepts that showcase Share Menus in action

4. COPY FOR IN-APP SHARE MESSAGE: The text that appears when a user shares their menu via iMessage/WhatsApp (under 160 chars, makes the recipient curious enough to click)

5. INFLUENCER BRIEF: 1-paragraph brief for influencers to show off Share Menus naturally (e.g. hosting a dinner party, making menus before a party)

6. PAID AD COPY: Write 3 short ad variants (Facebook/Instagram) targeting people interested in hosting and entertaining

7. GROWTH HOOK: One insight about why Share Menus is a viral loop (for pitching to press/investors)

App Store: {APP_STORE}""",
"share_menus_campaign.txt", "Share Menus Viral Campaign")


# ── 8. 90-Day Marketing Roadmap ───────────────────────────────────────────────
generate(f"""Write a 90-day Harvard MBA-level marketing roadmap for Spirit Library.

Context:
- Spirit Library: iOS cocktail app, 1,700+ recipes, live on App Store
- Current: just launched, building initial user base
- Resources: small budget, 1 founder (Steven), autonomous AI marketing agent running 2 Instagram posts/day
- Goal: 10,000 downloads in 90 days

Framework: Use a Week-by-Week plan for the first 30 days, then Monthly milestones for Days 31-90.

Include:
- Channel prioritization (which channels to attack in what order and why)
- Week 1-4 specific daily/weekly actions
- KPIs to track (what success looks like at each milestone)
- Partnership sequencing (what to close first)
- Content flywheel (how automated posts build compounding reach)
- One "big bet" moonshot play that could 10x the trajectory
- What NOT to do (avoid common early-stage marketing traps)

Be specific, tactical, and Harvard-honest — identify the real bottlenecks, not just the optimistic plan.""",
"90_day_roadmap.txt", "90-Day Marketing Roadmap")


# ── 9. Find 20 more press contacts ────────────────────────────────────────────
generate("""List 20 specific journalists, editors, and writers who cover cocktail/spirits apps, food tech, or consumer apps — with their known email patterns or publication contact methods.

Focus on:
- Food & Wine, Punch, Eater, The Infatuation, VinePair, Imbibe, Tasting Panel
- Tech/startup coverage: TechCrunch, The Verge, Product Hunt
- Lifestyle: Bon Appétit, Saveur, TASTE
- App review blogs and newsletters

For each, provide:
- Name
- Publication
- Beat (what they cover)
- Known email or how to reach them (editorial@ format if unknown)
- Why Spirit Library is a fit for their beat

Format as a clean list, 20 entries.""",
"press_contacts.txt", "Press Contacts List")


print(f"\n✅ All marketing assets written to marketing_assets/")
print("\nFiles created:")
for f in sorted(OUT.glob("*.txt")):
    size = f.stat().st_size
    print(f"  {f.name} ({size:,} bytes)")
