"""
Find cocktail/lifestyle app journalists with real, inferable email patterns.
Focus on publications that actually cover apps and have submission processes.
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
OUT = Path('outreach/targets/press_v2.json')

targets = [
    ("Imbibe Magazine", "imbibemagazine.com", "cocktail culture magazine", "covers apps, gear, and tools for cocktail enthusiasts"),
    ("VinePair", "vinepair.com", "drinks media brand", "covers apps and technology in the drinks space"),
    ("The Infatuation", "theinfatuation.com", "food and drink media", "NYC-based, covers drinking culture and tools"),
    ("Food52", "food52.com", "food and cooking media", "covers cocktail apps, recipe tools, kitchen technology"),
    ("Serious Eats", "seriouseats.com", "food media brand", "covers cocktail techniques, tools, and apps"),
    ("Liquor.com", "liquor.com", "spirits and cocktail media", "dedicated spirits/cocktail site, covers apps and tools"),
    ("The Spirits Business", "thespiritsbusiness.com", "spirits industry trade publication", "covers apps, technology, and consumer tools in the spirits industry"),
    ("Whisky Advocate", "whiskyadvocate.com", "whisky enthusiast magazine", "covers apps and digital tools for spirit enthusiasts"),
    ("Tasting Panel Magazine", "tastingpanelmag.com", "beverage industry trade", "covers technology and apps for the hospitality industry"),
    ("Eater", "eater.com", "food and restaurant media", "covers food apps, drink apps, and restaurant technology"),
    ("Grub Street", "grubstreet.com", "New York Magazine food vertical", "covers NYC food and drink culture, apps"),
    ("The Manual", "themanual.com", "men's lifestyle media", "covers cocktail apps, home bar gear, spirits"),
    ("Gear Patrol", "gearpatrol.com", "men's gear and lifestyle", "covers apps, tools, and gear for home bartending"),
    ("Cool Material", "coolmaterial.com", "men's lifestyle", "covers apps, home bar gear and cocktail tools"),
    ("Thrillist", "thrillist.com", "food and lifestyle media", "covers drinking apps, cocktail culture, food tech"),
]

results = []
print(f"\n📰 Researching {len(targets)} press targets...\n")

for i, (pub, domain, category, context) in enumerate(targets, 1):
    prompt = f"""From your training knowledge, provide contact information for pitching {pub} ({domain}) about a new iOS cocktail app.

Publication type: {category}
Context: {context}

Spirit Library pitch angle: New iOS cocktail app, 1,700+ recipes, My Bar feature (add bottles → discover what you can make), Allergies filter, Share Menus feature. Free app.

Provide:
1. The best contact email for app/product tips (tips@, editors@, hello@, specific writer email if known)
2. Whether they have a formal submission process
3. The right angle for this specific publication
4. Whether they're likely to cover this (yes/maybe/unlikely)

Return ONLY this JSON:
{{
  "publication": "{pub}",
  "domain": "{domain}",
  "contact_email": "email or null",
  "submission_url": "URL or null",
  "contact_method": "email/form/social",
  "pitch_angle": "one sentence tailored to this publication",
  "coverage_likelihood": "high/medium/low",
  "beat": "what section/writer covers this"
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
            print(f"  [{i}/{len(targets)}] ✓ {pub}: {result.get('contact_email','no email')} [{result.get('coverage_likelihood','?')}]")
        else:
            print(f"  [{i}/{len(targets)}] ? {pub}: no data")
        time.sleep(3)
    except Exception as e:
        print(f"  [{i}/{len(targets)}] ✗ {e}")
        time.sleep(3)

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(results, indent=2))
print(f"\n✅ {len(results)} press contacts → {OUT}")

# Send emails to high-likelihood contacts with emails
PITCH = """Hi {pub} Team,

I'm Steven Samori, founder of Spirit Library — a new iOS cocktail app worth putting on your radar.

{angle}

The quick facts:
• 1,700+ cocktail recipes (classic and contemporary)
• My Bar: add your home bottles → instantly see every cocktail you can make
• Flavor Search across 15 profiles (Citrus, Bitter, Smoky, Herbal, Tropical…)
• Occasion Search: Date Night, Brunch, Party, After Dinner, Celebration, and more
• Allergies filter: nuts, dairy, gluten, eggs, soy, citrus, shellfish
• Share Menus: curate and send a cocktail menu to guests before events
• 140+ ingredient substitutions
• Free, no ads, no paywall

App Store: {app_store}

Happy to provide screenshots, a demo walkthrough, promo codes, or a specific cocktail recipe to feature. What works for you?

Best,
Steven Samori
Founder, Spirit Library
claudesonnet111@gmail.com"""

print("\n📧 Sending pitches to high-likelihood contacts...")
sent = 0
for r in results:
    email = r.get('contact_email')
    likelihood = r.get('coverage_likelihood', 'low')
    if email and likelihood in ('high', 'medium') and '@' in str(email):
        try:
            body = PITCH.format(
                pub=r['publication'],
                angle=r.get('pitch_angle', 'Spirit Library is a smart cocktail recipe app with features your readers will love.'),
                app_store=APP_STORE
            )
            msg = MIMEMultipart()
            msg['From'] = GMAIL_USER
            msg['To'] = email
            msg['Subject'] = f"App Pitch: Spirit Library — Cocktail App with 1,700+ Recipes ({r['publication']})"
            msg.attach(MIMEText(body, 'plain'))
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
                s.login(GMAIL_USER, GMAIL_PASS)
                s.send_message(msg)
            print(f"  ✓ Sent → {email} ({r['publication']})")
            sent += 1
            time.sleep(4)
        except Exception as e:
            print(f"  ✗ {email}: {e}")

print(f"\n✅ Sent {sent} press pitches from new contacts list.")
