"""
Mocktails / Non-Alcoholic Campaign — full marketing push.
1. Find and email NA brands (Seedlip, Lyre's, Monday, Ghia, etc.)
2. Find sober-curious media/press contacts
3. Find NA influencers
4. Write email campaign copy
5. Write Instagram content series
6. Write partnership pitch deck
"""
import anthropic, os, json, re, time, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
GMAIL_USER = os.environ['GMAIL_USER']
GMAIL_PASS = os.environ['GMAIL_APP_PASSWORD']
APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"
OUT = Path('marketing_assets/mocktails')
OUT.mkdir(parents=True, exist_ok=True)
TARGETS_DIR = Path('outreach/targets')

# ══════════════════════════════════════════════════════════════════════════════
# PART 1: FIND NON-ALCOHOLIC BRAND PARTNERS
# ══════════════════════════════════════════════════════════════════════════════

NA_BRANDS = [
    ("Seedlip", "seedlipdrinks.com", "non-alcoholic spirits", "Pioneering NA spirit brand, acquired by Diageo, global distribution"),
    ("Lyre's Spirit Co", "lyres.com", "non-alcoholic spirits", "Full range of NA spirit alternatives — gin, whiskey, rum, etc."),
    ("Monday Zero Alcohol", "mondaygin.com", "zero-alcohol spirits", "Zero-alcohol gin, whiskey, mezcal. LA-based, fast-growing"),
    ("Ritual Zero Proof", "ritualzeroproof.com", "zero-proof spirits", "Whiskey, gin, tequila alternatives. Backed by DiageoX"),
    ("Ghia", "drinkghia.com", "non-alcoholic aperitif", "Stylish Mediterranean aperitif, strong DTC brand, celebrity following"),
    ("Curious Elixirs", "curiouselixirs.com", "booze-free cocktails", "Ready-to-drink NA cocktails, subscription model"),
    ("Kin Euphorics", "kineuphorics.com", "euphoric beverages", "Adaptogens + nootropics drinks, wellness-cocktail crossover"),
    ("Free Spirits", "drinkfreespirits.com", "spirit alternatives", "The Spirit of Gin, Bourbon, Tequila — NA alternatives"),
    ("Wilderton", "wilderton.com", "botanical spirits", "Portland-based NA botanical spirits, zero sugar"),
    ("Three Spirit", "threespiritdrinks.com", "plant-powered elixirs", "UK-based, functional plant spirits, Livener/Nightcap/Social"),
    ("Spiritless", "spiritless.com", "Kentucky 74", "NA bourbon alternative, Kentucky-made, bartender-endorsed"),
    ("CleanCo", "cleancodrinks.com", "clean spirits", "Spencer Matthews brand, UK-based NA spirits"),
    ("Proteau", "drinkproteau.com", "non-alcoholic drinks", "John deBary's NA botanical drink, bar industry credibility"),
    ("Hiyo", "drinkhiyo.com", "social tonic", "NA social tonic with adaptogens, designed for social occasions"),
    ("Athletic Brewing", "athleticbrewing.com", "NA craft beer", "Adjacent market — largest NA craft brewery, massive partnerships budget"),
    ("Surely Wines", "drinksurelywines.com", "NA wine", "Non-alcoholic wine brand, growing category"),
    ("Mixoloshe", "mixoloshe.com", "NA craft cocktails", "Premium ready-to-drink NA cocktails, female-founded"),
    ("Optimist Drinks", "optimistdrinks.com", "NA botanical spirits", "LA-based, bright citrus-forward NA spirits"),
    ("De Soi", "desoi.com", "NA aperitifs", "Katy Perry's NA aperitif brand, plant-based, massive PR reach"),
    ("Casamara Club", "casamaraclub.com", "leisure sodas", "Premium Italian-style amaro sodas, NA, craft bar scene credibility"),
]

results = []
print(f"\n🍹 MOCKTAIL CAMPAIGN — Researching {len(NA_BRANDS)} NA brands...\n")

for i, (brand, domain, category, context) in enumerate(NA_BRANDS, 1):
    prompt = f"""From training knowledge, find the partnership/marketing contact at {brand} ({domain}).

Context: {context}
Category: {category}

Spirit Library pitch for NA brands: Our iOS app has 1,700+ cocktail recipes including a growing mocktail/non-alcoholic section. We want to feature {brand}'s products in our NA recipes database, create custom mocktail recipes using their spirit, and offer Cocktail of the Day sponsorship for the NA category.

Find:
1. Marketing/partnerships contact email
2. Instagram handle
3. Their most likely interest in this partnership

Return ONLY JSON:
{{
  "brand": "{brand}",
  "domain": "{domain}",
  "category": "{category}",
  "contact_email": "email or null",
  "contact_method": "email/form/instagram",
  "instagram_handle": "@handle or null",
  "pitch_angle": "one tailored sentence about why this partnership makes sense for them",
  "response_likelihood": "high/medium/low"
}}"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            result = json.loads(match.group())
            result['researched_at'] = datetime.utcnow().isoformat()
            results.append(result)
            email = result.get('contact_email') or result.get('contact_method', '?')
            print(f"  [{i}/{len(NA_BRANDS)}] ✓ {brand}: {email}")
        time.sleep(3)
    except Exception as e:
        print(f"  [{i}/{len(NA_BRANDS)}] ✗ {e}")
        time.sleep(3)

(TARGETS_DIR / 'na_brands.json').write_text(json.dumps(results, indent=2))
print(f"\n✅ {len(results)} NA brand contacts → outreach/targets/na_brands.json")


# ══════════════════════════════════════════════════════════════════════════════
# PART 2: FIND SOBER-CURIOUS / NA MEDIA CONTACTS
# ══════════════════════════════════════════════════════════════════════════════

NA_MEDIA = [
    ("Dry Atlas", "dryatlas.com", "NA beverage review platform"),
    ("The Sober Curator", "thesobercurator.com", "sober lifestyle media"),
    ("Sober Girl Society", "sobergirlsociety.com", "sober women community"),
    ("Club Soda", "joinclubsoda.com", "mindful drinking movement UK"),
    ("The Zero Proof", "thezeroproof.com", "NA cocktail recipes and reviews"),
    ("Mindful Drinking Festival", "mindfuldrinker.co.uk", "UK mindful drinking events"),
    ("Boisson", "boisson.co", "NA bottle shop and media"),
    ("Spirited Away NYC", "spiritedawaynyc.com", "NYC NA bottle shop"),
    ("Sans Bar", "sansbar.com", "alcohol-free bar concept"),
    ("Spruce magazine", "spruce.com", "food and lifestyle media"),
]

media_results = []
print(f"\n📰 Researching {len(NA_MEDIA)} sober-curious media contacts...\n")

for i, (outlet, domain, desc) in enumerate(NA_MEDIA, 1):
    prompt = f"""From training knowledge, find the editorial/partnerships contact at {outlet} ({domain}).

Description: {desc}

Spirit Library pitch: Our cocktail app is expanding its non-alcoholic section. We want coverage as the app that serves BOTH cocktail enthusiasts and the sober-curious community. Our Allergies filter and Flavor Search work perfectly for NA drinks.

Find the best email to pitch.

Return ONLY JSON:
{{
  "outlet": "{outlet}",
  "domain": "{domain}",
  "contact_email": "email or null",
  "contact_method": "email/form",
  "pitch_angle": "one tailored sentence",
  "coverage_likelihood": "high/medium/low"
}}"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            result = json.loads(match.group())
            result['researched_at'] = datetime.utcnow().isoformat()
            media_results.append(result)
            print(f"  [{i}/{len(NA_MEDIA)}] ✓ {outlet}: {result.get('contact_email') or result.get('contact_method','?')}")
        time.sleep(3)
    except Exception as e:
        print(f"  [{i}/{len(NA_MEDIA)}] ✗ {e}")
        time.sleep(3)

(TARGETS_DIR / 'na_media.json').write_text(json.dumps(media_results, indent=2))
print(f"\n✅ {len(media_results)} NA media contacts → outreach/targets/na_media.json")


# ══════════════════════════════════════════════════════════════════════════════
# PART 3: FIND NA/SOBER-CURIOUS INFLUENCERS
# ══════════════════════════════════════════════════════════════════════════════

NA_INFLUENCERS = [
    ("The Mocktail Manual", "Instagram", "NA cocktail recipe content, growing following"),
    ("Sober Cheers (Jordan Gunn)", "Instagram/TikTok", "sober lifestyle, NA drink reviews"),
    ("Zero Proof Nation", "Instagram", "NA cocktail recipes and brand reviews"),
    ("The Sober Curator (Alysse Bryson)", "Instagram", "curates sober lifestyle content, events"),
    ("Drink Monday (content account)", "Instagram/TikTok", "Monday brand's content account, NA cocktails"),
    ("It's Not Drinking (Hilary Sheinbaum)", "Instagram", "sober-curious journalist, author of The Dry Challenge"),
    ("NA Beer Club", "Instagram", "NA beverage reviews, growing community"),
    ("Mocktail Mom", "Instagram/TikTok", "family-friendly NA drink recipes, relatable parenting angle"),
    ("Derek Brown (@ideasimprove)", "Instagram", "former bar owner, now sober, Dry January advocate, industry credibility"),
    ("Tiffany Baker (sober.tiff)", "TikTok", "sober lifestyle, NA recipes, 100k+ followers"),
]

inf_results = []
print(f"\n🌿 Researching {len(NA_INFLUENCERS)} NA influencers...\n")

for i, (name, platform, context) in enumerate(NA_INFLUENCERS, 1):
    prompt = f"""From training knowledge, provide contact details for {name} ({platform}).

Context: {context}

Pitch: Spirit Library is expanding its non-alcoholic recipe section. We want to create a custom mocktail recipe named after them in the app + potential paid collaboration.

Return ONLY JSON:
{{
  "name": "{name}",
  "platform": "{platform}",
  "instagram_handle": "@handle or null",
  "contact_email": "email or null",
  "contact_method": "email/DM/form",
  "audience_size": "estimate",
  "pitch_angle": "one sentence",
  "tier": "nano/micro/mid/macro"
}}"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            result = json.loads(match.group())
            result['researched_at'] = datetime.utcnow().isoformat()
            inf_results.append(result)
            print(f"  [{i}/{len(NA_INFLUENCERS)}] ✓ {name}: {result.get('instagram_handle') or result.get('contact_method','?')}")
        time.sleep(3)
    except Exception as e:
        print(f"  [{i}/{len(NA_INFLUENCERS)}] ✗ {e}")
        time.sleep(3)

(TARGETS_DIR / 'na_influencers.json').write_text(json.dumps(inf_results, indent=2))
print(f"\n✅ {len(inf_results)} NA influencer contacts → outreach/targets/na_influencers.json")


# ══════════════════════════════════════════════════════════════════════════════
# PART 4: SEND EMAILS TO NA BRANDS
# ══════════════════════════════════════════════════════════════════════════════

NA_BRAND_EMAIL = """Hi {brand} Team,

I'm Steven Samori, founder of Spirit Library — an iOS cocktail app with 1,700+ recipes, now live on the App Store.

I'm reaching out because we're building out our **non-alcoholic and mocktail recipe section** and {brand} is exactly the kind of brand we want to feature front and center.

Here's what we have in mind:

**1. Featured NA Recipes** — We'll create custom cocktail recipes using {brand}'s products as the hero ingredient, added permanently to our 1,700+ recipe database. Your spirit gets discovered every time someone searches by flavor, occasion, or ingredient.

**2. "Cocktail of the Day" NA Sponsorship** — Our daily featured cocktail spotlight, seen by every active user. We're creating a dedicated non-alcoholic category and offering founding sponsor pricing: **$500/month** with category exclusivity.

**3. Ingredient Search Placement** — When our users search "non-alcoholic gin" or browse their My Bar inventory, your product appears as a featured ingredient with linked cocktail suggestions.

The sober-curious audience is massive and growing — and they're underserved in cocktail apps. Spirit Library is one of the only apps that treats NA drinks with the same craft and respect as their alcoholic counterparts. {angle}

Would love 15 minutes to share our user metrics and explore what works for {brand}.

Download Spirit Library: {app_store}

Best,
Steven Samori
Founder, Spirit Library
claudesonnet111@gmail.com"""

NA_MEDIA_EMAIL = """Hi {outlet} Team,

I'm Steven Samori, founder of Spirit Library — an iOS cocktail app with 1,700+ recipes.

We're expanding our non-alcoholic and mocktail recipe section and I wanted to put this on your radar as a story:

**The angle:** Spirit Library is one of the only cocktail apps that treats non-alcoholic drinks with the same craft attention as traditional cocktails. Our Flavor Search (filter by Citrus, Herbal, Smoky, Tropical), Occasion Search (Date Night, Brunch, Celebration), and Allergies filter all work seamlessly for NA recipes.

{angle}

We're also partnering with NA spirit brands to feature their products as hero ingredients in our recipe database — making it easy for sober-curious users to discover exactly what to make and how.

Happy to provide app access, founder interview, or a specific NA recipe to feature. What works for {outlet}?

Download: {app_store}

Best,
Steven Samori
Founder, Spirit Library
claudesonnet111@gmail.com"""

def send_email(to, subject, body):
    msg = MIMEMultipart()
    msg['From'] = GMAIL_USER
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(msg)
    print(f"    ✓ Sent → {to}")

# Send brand emails
print("\n📧 Sending NA brand partnership emails...")
sent_brands = 0
for r in results:
    email = r.get('contact_email')
    if email and '@' in str(email):
        try:
            body = NA_BRAND_EMAIL.format(
                brand=r['brand'],
                angle=r.get('pitch_angle', ''),
                app_store=APP_STORE
            )
            send_email(email, f"Non-Alcoholic Partnership — Spirit Library x {r['brand']}", body)
            sent_brands += 1
            time.sleep(4)
        except Exception as e:
            print(f"    ✗ {r['brand']}: {e}")

# Send media emails
print("\n📰 Sending NA media pitches...")
sent_media = 0
for r in media_results:
    email = r.get('contact_email')
    if email and '@' in str(email):
        try:
            body = NA_MEDIA_EMAIL.format(
                outlet=r['outlet'],
                angle=r.get('pitch_angle', ''),
                app_store=APP_STORE
            )
            send_email(email, f"App Story: Spirit Library Expands Non-Alcoholic Recipe Section", body)
            sent_media += 1
            time.sleep(4)
        except Exception as e:
            print(f"    ✗ {r['outlet']}: {e}")

print(f"\n✅ MOCKTAIL CAMPAIGN CONTACTS COMPLETE")
print(f"   NA brands researched: {len(results)} | Emails sent: {sent_brands}")
print(f"   NA media researched: {len(media_results)} | Emails sent: {sent_media}")
print(f"   NA influencers found: {len(inf_results)}")
