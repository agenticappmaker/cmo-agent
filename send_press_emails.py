"""
Send press pitches to food/drink/tech journalists about Spirit Library.
"""
import smtplib, os, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

GMAIL_USER = os.environ['GMAIL_USER']
GMAIL_PASS = os.environ['GMAIL_APP_PASSWORD']
APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"

PRESS_CONTACTS = [
    {
        "to": "editors@punchdrink.com",
        "outlet": "Punch",
        "beat": "cocktail culture",
        "subject": "App Pitch: Spirit Library — 1,700 Recipes + Smart Home Bar for iOS"
    },
    {
        "to": "tips@eater.com",
        "outlet": "Eater",
        "beat": "food and drink apps",
        "subject": "New App: Spirit Library Makes Your Home Bar Smarter"
    },
    {
        "to": "editors@vinepair.com",
        "outlet": "VinePair",
        "beat": "drinks culture and apps",
        "subject": "App Tip: Spirit Library — Cocktail App with 1,700+ Recipes + Ingredient Search"
    },
    {
        "to": "editors@imbibemagazine.com",
        "outlet": "Imbibe",
        "beat": "cocktail culture",
        "subject": "New iOS App for Cocktail Enthusiasts: Spirit Library"
    },
    {
        "to": "tips@techcrunch.com",
        "outlet": "TechCrunch",
        "beat": "consumer apps",
        "subject": "App Launch: Spirit Library — AI-Powered Cocktail App Goes Live on iOS"
    },
    {
        "to": "tips@theverge.com",
        "outlet": "The Verge",
        "beat": "apps and tech",
        "subject": "New App: Spirit Library Turns Your Home Bar Into a Smart Cocktail Engine"
    },
    {
        "to": "letters@bonappetit.com",
        "outlet": "Bon Appétit",
        "beat": "food, drink, and culture",
        "subject": "App Pitch: Spirit Library — the Cocktail App for People Who Actually Cook"
    },
    {
        "to": "editor@tastecooking.com",
        "outlet": "TASTE",
        "beat": "food and drink",
        "subject": "App: Spirit Library — 1,700 Cocktail Recipes, Now on iOS"
    },
]

PITCH_BODY = """Hi {outlet} Team,

I'm Steven Samori, founder of Spirit Library — a new iOS cocktail app I wanted to put on your radar.

**The short version:** Spirit Library has 1,700+ cocktail recipes and a feature called My Bar — you add your bottles once, and the app instantly shows you every cocktail you can make right now. It also filters by flavor profile, occasion, and now allergies.

**Why it's a story:**
- The home cocktail market exploded post-pandemic and hasn't slowed. But the app ecosystem is still stuck on static recipe lists.
- Spirit Library treats your home bar like a smart ingredient database — more like a cooking app than a recipe card.
- We built a Share Menus feature so hosts can send guests an interactive cocktail menu before they arrive. Every shared menu is a small word-of-mouth loop.
- Coming soon: tap a recipe → order missing ingredients via Instacart or DoorDash, directly in the app.

**Download:** {app_store}

Happy to provide demo access, hi-res screenshots, founder interview, or a cocktail recipe to feature. What works for {outlet}?

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
    print(f"  ✓ Sent → {to}")


sent, failed = [], []

print("\n📰 Sending press pitches...\n")
for c in PRESS_CONTACTS:
    try:
        body = PITCH_BODY.format(outlet=c['outlet'], app_store=APP_STORE)
        send_email(c['to'], c['subject'], body)
        sent.append(c['to'])
        time.sleep(4)
    except Exception as e:
        print(f"  ✗ {c['to']}: {e}")
        failed.append(c['to'])

print(f"\n✅ Press pitches: {len(sent)} sent | {len(failed)} failed")
if failed:
    print(f"Failed: {failed}")
