"""
Find and email 20 more spirits brands — mid-tier and craft brands
more likely to respond than the big ones already contacted.
Small batch craft distilleries are underserved and actively looking for partnerships.
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

# Mid-tier and craft brands — more likely to respond, underserved by big apps
TARGETS = [
    ("St. George Spirits", "stgeorgespirits.com", "craft distillery", "California craft distillery, gins, whiskeys, eau de vie — cult following"),
    ("Empirical Spirits", "empiricalspirits.com", "avant-garde spirits", "Copenhagen spirits brand, experimental, editorial appeal"),
    ("Forthave Spirits", "forthavespirits.com", "craft NYC distillery", "Brooklyn distillery, aperitifs and spirits"),
    ("Singani 63", "singani63.com", "Bolivian spirit", "Steven Soderbergh's Bolivian spirit brand, unique positioning"),
    ("Giffard Liqueurs", "giffard.com", "French liqueur brand", "Premium French liqueurs used in hundreds of Spirit Library recipes"),
    ("Bittermens", "bittermens.com", "artisan bitters", "Artisan bitters brand — core ingredient in many Spirit Library recipes"),
    ("Scrappy's Bitters", "scrappysbitters.com", "craft bitters", "Seattle craft bitters, used widely in cocktail recipes"),
    ("Haus Alpenz", "alpenz.com", "spirits importer", "US importer for Batavia Arrack, Zirbenz, Dolin — specialty ingredients"),
    ("Rhum Clément", "rhum-clement.com", "Martinique rum", "Premium agricole rum brand, strong cocktail culture following"),
    ("Del Maguey Mezcal", "delmaguey.com", "single village mezcal", "Pioneering single village mezcal brand, cocktail bar staple"),
    ("Fords Gin", "fordsgin.com", "bartender's gin", "Created specifically for cocktails, strong on-trade relationships"),
    ("Código 1530", "codigo1530.com", "premium tequila", "Rosa tequila, celebrity partnership history, cocktail-forward"),
    ("The Bitter Truth", "the-bitter-truth.com", "bitters and liqueurs", "German bitters brand, essential cocktail ingredients"),
    ("Lustau Sherry", "lustau.es", "Spanish sherry", "Sherry is trending in cocktails — Spirit Library has dozens of sherry cocktail recipes"),
    ("Pierre Ferrand", "ferrandcognac.com", "Cognac and liqueurs", "Maison Ferrand makes Cognac, Plantation Rum, Citadelle Gin, Dry Curaçao"),
]

results = []
print(f"\n🥃 Researching {len(TARGETS)} craft/mid-tier spirits brands...\n")

for i, (brand, domain, category, context) in enumerate(TARGETS, 1):
    prompt = f"""From training knowledge, find the best partnership contact at {brand} ({domain}).

Context: {context}
Category: {category}

Spirit Library pitch: iOS cocktail app, 1,700+ recipes. Their products appear in our recipe database.
Sponsorship opportunity: Cocktail of the Day featuring their spirit ($500/month founding rate).

Provide the marketing/partnerships contact — email preferred.

Return ONLY JSON:
{{
  "brand": "{brand}",
  "contact_name": "name or null",
  "contact_title": "title or null",
  "contact_email": "email or null",
  "contact_method": "email/form/instagram",
  "instagram_handle": "@handle or null",
  "pitch_angle": "one tailored sentence",
  "response_likelihood": "high/medium/low"
}}"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            result = json.loads(match.group())
            result['researched_at'] = datetime.utcnow().isoformat()
            results.append(result)
            print(f"  [{i}/{len(TARGETS)}] ✓ {brand}: {result.get('contact_email') or result.get('contact_method','?')}")
        time.sleep(3)
    except Exception as e:
        print(f"  [{i}/{len(TARGETS)}] ✗ {e}")
        time.sleep(3)

# Save
out = Path('outreach/targets/brands_v2.json')
out.write_text(json.dumps(results, indent=2))
print(f"\n✅ {len(results)} brands → {out}")

# Email the ones with addresses
PITCH = """Hi {name},

I'm Steven Samori, founder of Spirit Library — an iOS cocktail app with 1,700+ recipes, now live on the App Store.

{angle}

{brand}'s products appear throughout our recipe database — your spirit is exactly the kind of ingredient our users are excited about. I wanted to reach out about our **Cocktail of the Day** sponsorship: one brand per spirit category, featured daily to all active users.

We're offering founding sponsor pricing ($500/month) to craft brands before we raise rates in Q3. Category exclusivity is included — no competing brands while you sponsor.

Would love to share our user metrics and rate card. 15 minutes this week?

Download Spirit Library: {app_store}

Best,
Steven Samori
Founder, Spirit Library
claudesonnet111@gmail.com"""

print("\n📧 Sending to brands with emails...")
sent = 0
for r in results:
    email = r.get('contact_email')
    if email and '@' in str(email) and r.get('response_likelihood') in ('high', 'medium'):
        try:
            body = PITCH.format(
                name=r.get('contact_name') or 'Team',
                brand=r['brand'],
                angle=r.get('pitch_angle', ''),
                app_store=APP_STORE
            )
            msg = MIMEMultipart()
            msg['From'] = GMAIL_USER
            msg['To'] = email
            msg['Subject'] = f"Cocktail of the Day Sponsorship — Spirit Library x {r['brand']}"
            msg.attach(MIMEText(body, 'plain'))
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
                s.login(GMAIL_USER, GMAIL_PASS)
                s.send_message(msg)
            print(f"  ✓ {r['brand']} → {email}")
            sent += 1
            time.sleep(4)
        except Exception as e:
            print(f"  ✗ {r['brand']}: {e}")

print(f"\n✅ Sent {sent} brand emails.")
