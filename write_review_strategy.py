"""
Write app review strategy + in-app prompt copy + email to app review sites.
App reviews are the single highest-ROI action for organic App Store growth.
"""
import anthropic, os, smtplib, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
GMAIL_USER = os.environ['GMAIL_USER']
GMAIL_PASS = os.environ['GMAIL_APP_PASSWORD']
APP_STORE = "https://apps.apple.com/app/spirit-library/id6746823938"
OUT = Path('marketing_assets')

# ── Write review strategy doc ─────────────────────────────────────────────────
resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2000,
    messages=[{"role": "user", "content": f"""Write a complete App Store review strategy for Spirit Library (iOS cocktail app, 1,700+ recipes).

Include:
1. THE OPTIMAL MOMENT TO ASK (behavioral triggers in the app — when is a user in the best emotional state to leave a review?)
2. IN-APP PROMPT COPY (3 variants for SKAdNetwork/StoreKit prompt — the pre-prompt that appears before the system dialog)
   - The pre-prompt must make users want to tap "Rate" not "Not Now"
   - Keep it under 100 words, warm and human
3. EMAIL SEQUENCE for asking early users to review:
   - Email 1: Day 3 after install (subject + body, 150 words)
   - Email 2: Day 7 after install, if no review (subject + body, 100 words, lighter touch)
4. REVIEW RESPONSE TEMPLATES:
   - Response to 5-star review (warm, personalized feel)
   - Response to 3-star review (acknowledge, promise improvement)
   - Response to 1-star review (professional, de-escalation)
5. GOAL: Getting from 0 to 50 reviews in 30 days — realistic tactics only

App Store: {APP_STORE}"""}]
)
(OUT / "review_strategy.txt").write_text(resp.content[0].text)
print("✓ Review strategy → marketing_assets/review_strategy.txt")


# ── Email app review sites ─────────────────────────────────────────────────────
REVIEW_SITES = [
    {
        "to": "tips@appadvice.com",
        "site": "AppAdvice",
        "subject": "App Review Request: Spirit Library — Cocktail Recipe App (iOS)"
    },
    {
        "to": "reviews@148apps.com",
        "site": "148Apps",
        "subject": "Review Submission: Spirit Library — 1,700+ Cocktail Recipes, Free iOS"
    },
    {
        "to": "contact@appsgonefree.com",
        "site": "Apps Gone Free",
        "subject": "Spirit Library — New iOS Cocktail App, Review Request"
    },
    {
        "to": "editor@appolicious.com",
        "site": "Appolicious",
        "subject": "Spirit Library App — Review Request"
    },
]

REVIEW_PITCH = """Hi {site} Team,

I'm Steven Samori, founder of Spirit Library — a new iOS cocktail app I'd love to submit for review consideration.

**Spirit Library** ({app_store}) is a smart home bar and cocktail recipe app with 1,700+ recipes. The standout feature is My Bar — users add their bottles and instantly see every cocktail they can make right now, filtered by flavor profile, occasion, or allergens.

Key features:
• 1,700+ cocktail recipes (classic and contemporary)
• My Bar: ingredient-based recipe discovery
• Flavor Search: 15 distinct profiles (Citrus, Bitter, Smoky, Herbal, etc.)
• Share Menus: curate and share a cocktail menu with party guests
• Allergy filter: nuts, dairy, gluten, eggs, soy, citrus, shellfish
• Recipe builder for custom cocktails
• 140+ ingredient substitutions
• Free, no ads, no paywall

Happy to provide promo codes, screenshots, demo video, or a phone walkthrough. What would be most helpful?

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

print("\n📱 Emailing app review sites...")
for c in REVIEW_SITES:
    try:
        body = REVIEW_PITCH.format(site=c['site'], app_store=APP_STORE)
        send_email(c['to'], c['subject'], body)
        time.sleep(4)
    except Exception as e:
        print(f"  ✗ {c['to']}: {e}")

print("\n✅ Done.")
